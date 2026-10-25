"""Settings for the v2 Decatur / DeKalb pull, which writes straight into Supabase.

Edit the values in the EDIT ME block. Everything else has sensible defaults.
The database password is never stored here: set DATABASE_URL in your shell, or
the scripts ask for it with hidden input.
"""
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
RAW_DIR = PROJECT_DIR / "raw"          # every raw response is saved here (gzipped)
LOG_DIR = PROJECT_DIR / "logs"

# ============================ EDIT ME ========================================
# A contact address the site operators can reach you at. Live pulls refuse to
# start until this is set (here, or with the PULL_CONTACT environment variable).
CONTACT = os.environ.get("PULL_CONTACT", "")

# City tax years to pull from the city bill portal (most recent first).
CITY_YEARS = [2026]
# County tax year sent to the county pages.
COUNTY_TAX_YEAR = 2026
# County GIS parcel layer. "auto" picks the newest Tax_Parcels_YYYY layer the
# county publishes; or name one explicitly, e.g. "Tax_Parcels_2026".
COUNTY_GIS_LAYER = "auto"
# =============================================================================

USER_AGENT_TMPL = ("DecaturSeniorExemptionProject/2.0 "
                   "(student civic research on unclaimed homestead exemptions; contact {contact})")

# --- politeness, per host ----------------------------------------------------
TIMEOUT = 60
MAX_RETRIES = 3                 # for network errors and 5xx only; blocks are handled separately
DELAY = {                       # base seconds between requests, plus up to 50% random jitter
    "gis": 0.5,
    "city": 3.0,
    "county": 2.0,
}
DAILY_BUDGET = {                # max requests per source per calendar day (all runs combined)
    "gis": 500,
    "city": 400,
    "county": 6000,
}
BLOCK_PAUSE_MINUTES = (15, 30)  # pause a random time in this range after a block
MAX_BLOCKS_PER_RUN = 2          # stop the run after this many blocks
ARCHIVE_KEEP = 3                # pre-run snapshots kept per table in the archive schema

# --- sources -----------------------------------------------------------------
CITY_GIS = ("https://services.arcgis.com/36QtML6Mf01B1N0W/arcgis/rest/services/"
            "City_of_Decatur_Parcels/FeatureServer/0/query")
COUNTY_GIS_ROOT = "https://services2.arcgis.com/IxVN2oUE9EYLSnPE/arcgis/rest/services"
COUNTY_GIS_WHERE = "TAX_DISTRICT='92'"          # 92 = City of Decatur

WILDFIRE_URL = ("https://d1ebsyxxbc7tep.cloudfront.net/data/"
                "2c947c35-9d67-4eaa-931c-626d7c539071/Wildfire/Records")
WILDFIRE_ORIGIN = "https://www.decaturgatax.com"

IASWORLD_URL = "https://publicaccess.dekalbtaxga.gov/datalets/datalet.aspx"
COUNTY_MODES_PRIMARY = ["dek_exemptions", "dek_profile"]
COUNTY_MODES_SECONDARY = ["mailing", "dek_sales", "residential"]
COUNTY_MODES_ALL = COUNTY_MODES_PRIMARY + COUNTY_MODES_SECONDARY


def user_agent():
    return USER_AGENT_TMPL.format(contact=CONTACT or "not-set")


def norm_pin(s):
    """'15 000 00 000 ' -> '15 000 00 000'; None / 'NO ID' -> None."""
    if not s:
        return None
    s = " ".join(str(s).split())
    if not s or s.upper() == "NO ID":
        return None
    return s
