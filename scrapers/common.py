"""Shared pieces for the v2 pull: Supabase connection, upserts, run log,
pre-run archive snapshots, and a polite HTTP session that notices blocks."""
import getpass
import gzip
import json
import logging
import os
import random
import re
import sys
import time
from datetime import date, datetime

import psycopg
import requests
from psycopg import sql

import config

log = logging.getLogger("decatur")


class Blocked(Exception):
    """The site is refusing or throttling us. Never record the item as done."""


class StopRun(Exception):
    """Stop the whole run cleanly (too many blocks, budget used up, time limit)."""

    def __init__(self, status, msg):
        super().__init__(msg)
        self.status = status


# ----------------------------------------------------------------- logging
def setup_logging(name):
    config.LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(),
                  logging.FileHandler(config.LOG_DIR / f"{name}.log")],
    )


# ----------------------------------------------------------------- database
def database_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("Paste your Supabase connection string (Session pooler URI, password filled in).")
        print("Input is hidden and is not saved anywhere.")
        url = getpass.getpass("DATABASE_URL: ").strip()
    if not url:
        sys.exit("No connection string given.")
    return url


def connect(url=None):
    url = url or database_url()
    kw = {} if "sslmode=" in url or "localhost" in url or "host=/" in url or "@/" in url else {"sslmode": "require"}
    conn = psycopg.connect(url, autocommit=False, connect_timeout=20,
                           keepalives=1, keepalives_idle=60, **kw)
    conn.execute("set statement_timeout = '120s'")
    conn.commit()
    return conn


class DB:
    """Holds the connection, the run id, table metadata, and does upserts.

    Every raw.* table is snapshotted into the archive schema (at most once per
    day) the first time a run writes to it, so a bad pull can always be undone.
    """

    def __init__(self, source, args=None, url=None, snapshot=True):
        self.url = url or database_url()
        self.conn = connect(self.url)
        self.source = source
        self.snapshot = snapshot
        self._cols = {}
        self._pk = {}
        self._touched = set()
        self.rows = 0
        cur = self.conn.execute(
            "insert into raw.pull_runs (source, args) values (%s, %s) returning run_id",
            (source, json.dumps(args or {}, default=str)))
        self.run_id = cur.fetchone()[0]
        self.conn.commit()
        self.fix_sequences()

    # -- connection resilience (Supabase pooler connections can drop on long runs)
    def reconnect(self):
        try:
            self.conn.close()
        except Exception:
            pass
        for attempt in range(1, 6):
            try:
                self.conn = connect(self.url)
                log.warning("reconnected to database")
                return
            except psycopg.OperationalError as e:
                log.warning("reconnect attempt %d failed: %s", attempt, e)
                time.sleep(15 * attempt)
        raise StopRun("failed", "lost the database connection")

    def execute(self, q, params=None):
        return self.conn.execute(q, params)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        try:
            self.conn.rollback()
        except Exception:
            pass

    def fix_sequences(self):
        """Keep identity counters ahead of existing ids (a CSV reload resets them)."""
        for t in ("city_bill_lines", "county_sales"):
            self.conn.execute(sql.SQL(
                "select setval(pg_get_serial_sequence({q}, 'id'), "
                "greatest((select coalesce(max(id), 0) from raw.{t}), 1))").format(
                    q=sql.Literal(f"raw.{t}"), t=sql.Identifier(t)))
        self.conn.commit()

    # -- metadata
    def columns(self, table):
        if table not in self._cols:
            cur = self.conn.execute(
                "select column_name, data_type from information_schema.columns "
                "where table_schema='raw' and table_name=%s", (table,))
            self._cols[table] = dict(cur.fetchall())
            cur = self.conn.execute(
                "select a.attname from pg_index i join pg_attribute a "
                "on a.attrelid=i.indrelid and a.attnum = any(i.indkey) "
                "where i.indrelid = %s::regclass and i.indisprimary", (f"raw.{table}",))
            self._pk[table] = [r[0] for r in cur.fetchall()]
        return self._cols[table]

    def _coerce(self, table, row):
        cols = self.columns(table)
        out = {}
        for k, v in row.items():
            if k not in cols:
                continue
            t = cols[k]
            if v is not None and t in ("bigint", "integer", "smallint"):
                try:
                    v = int(round(float(v)))
                except (TypeError, ValueError):
                    v = None
            out[k] = v
        return out

    # -- archive snapshots
    def touch(self, table):
        if not self.snapshot or table in self._touched:
            return
        self._touched.add(table)
        snap = f"{table}__{date.today():%Y%m%d}"
        exists = self.conn.execute("select to_regclass(%s)", (f"archive.{snap}",)).fetchone()[0]
        if not exists:
            log.info("archiving raw.%s -> archive.%s before writing", table, snap)
            self.conn.execute(sql.SQL("create table archive.{s} as table raw.{t}").format(
                s=sql.Identifier(snap), t=sql.Identifier(table)))
            self.conn.execute(sql.SQL("alter table archive.{s} enable row level security").format(
                s=sql.Identifier(snap)))
            self.conn.execute(sql.SQL("revoke all on archive.{s} from anon, authenticated").format(
                s=sql.Identifier(snap)))
            # keep only the newest ARCHIVE_KEEP snapshots of this table
            olds = [r[0] for r in self.conn.execute(
                "select tablename from pg_tables where schemaname='archive' and tablename like %s "
                "order by tablename desc", (f"{table}\\_\\_%",)).fetchall()][config.ARCHIVE_KEEP:]
            for o in olds:
                if re.fullmatch(re.escape(table) + r"__\d{8}", o):
                    log.info("dropping old snapshot archive.%s", o)
                    self.conn.execute(sql.SQL("drop table archive.{o}").format(o=sql.Identifier(o)))
            self.conn.commit()

    # -- writes
    def upsert(self, table, row, conflict=None):
        """INSERT ... ON CONFLICT (primary key, or `conflict`) DO UPDATE."""
        self.touch(table)
        row = self._coerce(table, row)
        cols = list(row)
        if conflict is None:
            keys = self._pk[table]
            target = sql.SQL("({})").format(sql.SQL(",").join(map(sql.Identifier, keys)))
        else:
            keys = conflict[1]
            target = sql.SQL("on constraint {}").format(sql.Identifier(conflict[0]))
        upd = [c for c in cols if c not in keys and c != "id"]
        action = (sql.SQL("do update set ") + sql.SQL(",").join(
            sql.SQL("{c}=excluded.{c}").format(c=sql.Identifier(c)) for c in upd)) if upd else sql.SQL("do nothing")
        q = sql.SQL("insert into raw.{t} ({cols}) values ({vals}) on conflict {target} {action}").format(
            t=sql.Identifier(table), cols=sql.SQL(",").join(map(sql.Identifier, cols)),
            vals=sql.SQL(",").join(sql.Placeholder() * len(cols)), target=target, action=action)
        self.conn.execute(q, [row[c] for c in cols])
        self.rows += 1

    def insert(self, table, row):
        self.touch(table)
        row = self._coerce(table, row)
        cols = list(row)
        q = sql.SQL("insert into raw.{t} ({cols}) values ({vals})").format(
            t=sql.Identifier(table), cols=sql.SQL(",").join(map(sql.Identifier, cols)),
            vals=sql.SQL(",").join(sql.Placeholder() * len(cols)))
        self.conn.execute(q, [row[c] for c in cols])
        self.rows += 1

    def delete(self, table, where, params):
        self.touch(table)
        self.conn.execute(sql.SQL("delete from raw.{t} where ").format(t=sql.Identifier(table)) + sql.SQL(where), params)

    # -- run log
    def requests_today(self, source):
        r = self.conn.execute(
            "select coalesce(sum(requests),0) from raw.pull_runs where source=%s "
            "and started_at >= date_trunc('day', now()) and run_id <> %s", (source, self.run_id)).fetchone()
        return int(r[0])

    def update_run(self, session=None, status=None, note=None):
        self.conn.execute(
            "update raw.pull_runs set requests=%s, rows_written=%s, blocks=%s, "
            "status=coalesce(%s::text, status), note=coalesce(%s::text, note), "
            "finished_at=case when %s::text is not null and %s::text <> 'running' then now() else finished_at end "
            "where run_id=%s",
            (session.calls if session else 0, self.rows, session.blocks if session else 0,
             status, note, status, status, self.run_id))
        self.conn.commit()


# ----------------------------------------------------------------- HTTP
class PoliteSession:
    """Fixed delay + jitter between requests, retries for network/5xx errors,
    a daily request budget, and block handling: on a block it pauses 15-30 min,
    and after MAX_BLOCKS_PER_RUN blocks it stops the run."""

    def __init__(self, source, budget_left, headers=None, live=True, max_minutes=None):
        if live and not config.CONTACT:
            sys.exit("Set a contact email first: edit CONTACT in config.py or run "
                     "`export PULL_CONTACT=you@example.com`. Sites ask scrapers to identify themselves.")
        self.source = source
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": config.user_agent()})
        if headers:
            self.s.headers.update(headers)
        self.delay = config.DELAY[source]
        self.budget_left = budget_left
        self.calls = 0
        self.blocks = 0
        self._last = 0.0
        self.deadline = time.monotonic() + max_minutes * 60 if max_minutes else None
        self.sleep = time.sleep          # replaced in tests

    def _wait(self):
        gap = self.delay * (1 + random.random() * 0.5) - (time.monotonic() - self._last)
        if gap > 0:
            self.sleep(gap)

    def check_limits(self):
        if self.calls >= self.budget_left:
            raise StopRun("stopped_budget", f"daily request budget reached ({self.calls} this run)")
        if self.deadline and time.monotonic() > self.deadline:
            raise StopRun("stopped_time", "time limit reached")

    def request(self, method, url, **kw):
        kw.setdefault("timeout", config.TIMEOUT)
        for attempt in range(1, config.MAX_RETRIES + 1):
            self.check_limits()
            self._wait()
            try:
                r = self.s.request(method, url, **kw)
                self._last = time.monotonic()
                self.calls += 1
                if r.status_code in (403, 429):
                    raise Blocked(f"HTTP {r.status_code}" +
                                  (f" Retry-After={r.headers.get('Retry-After')}" if r.headers.get("Retry-After") else ""))
                if r.status_code in (500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
                return r
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
                self._last = time.monotonic()
                backoff = min(120, self.delay * 4 * (2 ** attempt))
                log.warning("%s failed (%s); retry %d/%d in %.0fs", url[:70], e, attempt, config.MAX_RETRIES, backoff)
                if attempt == config.MAX_RETRIES:
                    raise
                self.sleep(backoff)

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def handle_block(self, why):
        """Call after catching Blocked. Pauses, or raises StopRun after too many."""
        self.blocks += 1
        log.warning("BLOCKED (%s) - block %d of %d allowed this run", why, self.blocks, config.MAX_BLOCKS_PER_RUN)
        if self.blocks >= config.MAX_BLOCKS_PER_RUN:
            raise StopRun("stopped_blocked", f"stopped after {self.blocks} blocks; last: {why}. "
                          "Wait several hours (ideally until tomorrow) before running again.")
        lo, hi = config.BLOCK_PAUSE_MINUTES
        mins = random.uniform(lo, hi)
        log.warning("pausing %.0f minutes before trying again", mins)
        self.sleep(mins * 60)
        self.delay *= 1.5               # come back slower
        log.warning("delay between requests is now %.1fs", self.delay)


# ----------------------------------------------------------------- raw files
def save_raw(path, text):
    path = path.with_suffix(path.suffix + ".gz")
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(text)
    return path


def read_raw(path):
    gz = path.with_suffix(path.suffix + ".gz")
    if gz.exists():
        with gzip.open(gz, "rt", encoding="utf-8", errors="replace") as f:
            return f.read()
    if path.exists():
        return path.read_text(errors="replace")
    return None


def now():
    return datetime.now()
