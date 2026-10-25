#!/usr/bin/env python3
"""Export decatur_tax.sqlite (read-only) to CSVs + a psql load script for Supabase.

Output (next to this script):
  data/<schema>.<table>.csv   one per table, header row; NULL = empty unquoted field, text always quoted
  load.sql                    psql script: truncates the target tables, \\copy-loads every CSV in one transaction
  run_load.sh                 asks for your Supabase connection string (hidden input) and runs load.sql
  expected_counts.json        row counts per table, for verification after the load

The SQLite file is opened read-only and is never modified.
"""
import json, os, sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(os.path.dirname(HERE), "decatur_tax.sqlite")
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

def schema_of(t):
    if t.startswith("census_"):
        return "census"
    if t.startswith("r_") or t.startswith("ref_"):
        return "analysis"
    return "raw"

def cell(v):
    if v is None:
        return ""
    if isinstance(v, bytes):
        v = v.decode("utf-8", "replace")
    if isinstance(v, str):
        return '"' + v.replace('"', '""') + '"'
    if isinstance(v, float):
        return repr(v)
    return str(v)

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY 1")]
counts, copies, targets = {}, [], []
for t in tables:
    s = schema_of(t)
    cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
    path = os.path.join(DATA, f"{s}.{t}.csv")
    n = 0
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(",".join(cols) + "\n")
        for row in con.execute(f'SELECT * FROM "{t}"'):
            f.write(",".join(cell(v) for v in row) + "\n")
            n += 1
    counts[f"{s}.{t}"] = n
    collist = ", ".join(f'"{c}"' for c in cols)
    targets.append(f"{s}.{t}")
    copies.append(f"\\echo loading {s}.{t} ({n} rows)\n\\copy {s}.{t} ({collist}) FROM 'data/{s}.{t}.csv' WITH (FORMAT csv, HEADER true)")

# map data (prepared separately from the parcel/street/city-limit GIS layers)
geo = [("geo.parcels", "parcel_id, source, geom", "geo_parcels.csv"),
       ("geo.streets", "name, road_class, geom", "geo_streets.csv"),
       ("geo.city_limits", "name, geom", "geo_city_limits.csv")]
for tgt, cols, fn in geo:
    if os.path.exists(os.path.join(DATA, fn)):
        with open(os.path.join(DATA, fn), encoding="utf-8") as f:
            counts[tgt] = sum(1 for _ in f) - 1
        targets.append(tgt)
        copies.append(f"\\echo loading {tgt}\n\\copy {tgt} ({cols}) FROM 'data/{fn}' WITH (FORMAT csv, HEADER true)")

with open(os.path.join(HERE, "load.sql"), "w") as f:
    f.write("\\set ON_ERROR_STOP on\nSET statement_timeout = 0;\nSET search_path = public, extensions;\nBEGIN;\n")
    f.write("TRUNCATE " + ", ".join(targets) + " RESTART IDENTITY;\n")
    f.write("\n".join(copies) + "\n")
    f.write("\\echo building census tract outlines\n"
            "UPDATE census.census_tracts SET geom = ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(geometry_geojson), 4326));\n")
    f.write("COMMIT;\nANALYZE;\n\\echo\n\\echo Done. All tables loaded in one transaction.\n")

with open(os.path.join(HERE, "run_load.sh"), "w") as f:
    f.write("""#!/bin/zsh
# Loads the exported CSVs into the decatur-exemptions Supabase project.
# Your connection string is read with hidden input and never written to disk.
set -e
cd "$(dirname "$0")"
if ! command -v psql >/dev/null 2>&1; then
  for p in /Applications/Postgres.app/Contents/Versions/latest/bin /opt/homebrew/opt/libpq/bin /usr/local/opt/libpq/bin; do [ -x "$p/psql" ] && export PATH="$p:$PATH"; done
fi
if ! command -v psql >/dev/null 2>&1; then
  echo "psql not found. Install Postgres.app from https://postgresapp.com (drag it into Applications), then run this script again."
  exit 1
fi
echo "Paste your Supabase connection string (Session pooler URI, with your password filled in), then press Enter:"
read -rs DBURL
echo
export PGSSLMODE=require
psql "$DBURL" -v ON_ERROR_STOP=1 -f load.sql
""")
os.chmod(os.path.join(HERE, "run_load.sh"), 0o755)
json.dump(counts, open(os.path.join(HERE, "expected_counts.json"), "w"), indent=1)
print(len(counts), "tables;", sum(counts.values()), "rows")
