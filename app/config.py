from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WEB_DIR = ROOT / "web"
STATE_DIR = ROOT / ".state"          # local demo store (gitignored); prod = encrypted DB
STATE_DIR.mkdir(exist_ok=True)

TODAY = date(2026, 7, 15)            # dataset README: use 2026-07-15 as "today"
GST_RATE = 0.18
ONE_BILL_DISCOUNT = {3: 0.05, 5: 0.08, 7: 0.10}   # products in bundle -> discount
SWITCH_SHIELD_MAX_MONTHS = 2         # credit up to 2 months of old provider spend
SWITCH_SHIELD_CAP_INR = 5000
LATE_DAY_CREDIT_SHARE = 1 / 30       # one day of monthly fee per late day
SAATHI_COMMISSION = 0.08             # 8% of year-1 MRR on digital closes
BAZAAR_CLUSTER_MIN_SHOPS = 5
BAZAAR_CLUSTER_DISCOUNT = 0.07
RETENTION_DAYS_IMAGES = 30
