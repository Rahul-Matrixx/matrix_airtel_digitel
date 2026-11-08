"""Deterministic rules engine: eligibility, bundle building and pricing.

Design rule: these rules decide WHAT is sold. Any language model only rephrases
the explanation of a bundle this module already produced; it can never add,
remove or price a product.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from functools import lru_cache

import pandas as pd

from . import config as C

SEGMENT_KEYS = {"micro": "Micro retail & services", "prof": "Professional offices",
                "multi": "Small multi-site businesses", "mfg": "Small manufacturers"}


@lru_cache(maxsize=1)
def catalogue() -> pd.DataFrame:
    df = pd.read_csv(C.DATA_DIR / "product_catalogue.csv", dtype=str).fillna("")
    for col in ["price_min_inr_per_month", "price_max_inr_per_month", "one_time_setup_inr",
                "min_contract_months", "min_employees", "min_sites", "typical_install_days"]:
        df[col] = df[col].astype(int)
    df["tiers"] = df["available_city_tiers"].str.split(";").apply(lambda xs: {int(x) for x in xs if x})
    df["needs_one_of"] = df["requires_one_of"].str.split("|").apply(lambda xs: [x for x in xs if x])
    df["segments"] = df["target_segments"].str.split(";").apply(set)
    return df.set_index("product_id")


@lru_cache(maxsize=1)
def city_tiers() -> dict[str, int]:
    leads = pd.read_csv(C.DATA_DIR / "smb_leads.csv", usecols=["city", "city_tier"])
    return leads.drop_duplicates("city").set_index("city")["city_tier"].astype(int).to_dict()


@dataclass
class Profile:
    segment: str = "micro"                 # micro | prof | multi | mfg
    business_type: str = ""
    city: str = ""
    city_tier: int = 2
    employees: int = 1
    sites: int = 1
    gstin_valid: bool = False              # set only after checksum + registry status check
    needs: set = field(default_factory=set)
    sim_lines: int | None = None
    cameras: int | None = None
    current_spend: int = 0                 # optional, owner-declared monthly telecom spend
    locked_in: bool = False                # owner says they are in a contract elsewhere
    contract_months: int = 12
    cluster_code: str | None = None
    language: str = "en"


NEED_TO_PRODUCT = {
    "sim": "P07", "upi": "P19", "pos": "P19", "whatsapp": "P15", "sms": "P14", "email": "P16",
    "backup": "P17", "website": "P18", "antivirus": "P20", "firewall": "P21", "wifi": "P22",
    "cctv": "P23", "iot": "P24", "fleet": "P25", "telephony": "P12", "tollfree": "P13",
    "failover": "P09", "sdwan": "P10", "static_ip": "P11",
}

SEGMENT_DEFAULT_NEEDS = {
    "micro": {"internet", "sim", "upi"},
    "prof": {"internet", "sim", "email", "antivirus", "backup", "wifi"},
    "multi": {"internet", "sim", "pos", "cctv", "wifi", "failover", "email"},
    "mfg": {"internet", "sim", "iot", "firewall", "email"},
}

PLAIN_WHY = {
    "P01": "fast, unlimited fibre for UPI, billing and video calls",
    "P02": "faster fibre so several staff can work online at once",
    "P03": "1 Gbps fibre with priority support for heavy users",
    "P04": "5G wireless broadband that works without digging for fibre — live in 2 days",
    "P05": "a dedicated line that is not shared, with a 99.5% uptime promise",
    "P06": "a 100 Mbps dedicated line with a 99.9% uptime promise for machines and ERP",
    "P07": "business SIMs with 50 GB data and unlimited calls",
    "P08": "premium SIMs with 150 GB data and priority care",
    "P09": "a backup router that keeps you online when the main line is down",
    "P10": "one dashboard to manage the internet at every site",
    "P11": "a fixed IP so you can view cameras or servers from outside",
    "P12": "business phone lines with IVR and call recording",
    "P13": "a free-to-call 1800 number for your customers",
    "P14": "10,000 SMS a month for offers and order alerts",
    "P15": "a verified WhatsApp channel with your catalogue",
    "P16": "email on your own domain plus documents and video meetings",
    "P17": "automatic backup of PCs and phones, 1 TB",
    "P18": "a domain and a simple 5-page website",
    "P19": "GST-ready billing with UPI and card acceptance on a tablet",
    "P20": "antivirus and ransomware protection",
    "P21": "a managed firewall watched by the Accel security team",
    "P22": "secure Wi-Fi with a separate network for customers",
    "P23": "HD cameras with 30-day cloud recording you can watch on your phone",
    "P24": "sensors that show machine uptime and energy use",
    "P25": "GPS trackers for your vehicles with a live map",
}


def unit_price(pid: str, p: Profile) -> int:
    """Inside a bundle every product is sold at the floor of its catalogue range;
    bought one by one it costs the top of the range (that gap is the Bill-Swap)."""
    return int(catalogue().loc[pid].price_min_inr_per_month)


def list_price(pid: str) -> int:
    return int(catalogue().loc[pid].price_max_inr_per_month)


def connectivity_choice(p: Profile) -> str:
    if p.segment == "mfg":
        return "P06" if p.employees >= 25 else ("P05" if p.employees >= 10 else "P02")
    if p.segment == "multi":
        return "P02"
    if p.segment == "prof":
        return "P02" if p.employees >= 5 else "P01"
    if not p.gstin_valid:
        return "P04"          # Lite rung of the Grow Ladder: 5G AirFiber, live in 2 days
    return "P01"


def default_qty(pid: str, p: Profile) -> int:
    per_site = {"P01", "P02", "P03", "P04", "P05", "P06", "P09", "P10", "P21", "P22"}
    if pid in per_site:
        return p.sites
    if pid in {"P07", "P08"}:
        return p.sim_lines or max(1, min(p.employees, 2 if p.segment == "micro" else 5))
    if pid == "P16" or pid == "P20":
        return max(1, min(p.employees, 10))
    if pid == "P23":
        return p.cameras or (2 * p.sites if p.segment != "mfg" else 4)
    if pid == "P24":
        return 10
    if pid == "P19":
        return p.sites
    return 1


def check_item(pid: str, p: Profile, bundle_ids: set[str]) -> str | None:
    """Return None if the product may be sold to this profile, else the plain reason."""
    row = catalogue().loc[pid]
    if p.city_tier not in row.tiers:
        return f"not sold in tier-{p.city_tier} cities yet"
    if p.employees < row.min_employees:
        return f"needs at least {row.min_employees} employees"
    if p.sites < row.min_sites:
        return f"needs at least {row.min_sites} sites"
    if row.requires_gstin == "Y" and not p.gstin_valid:
        return "needs a valid, active GSTIN"
    if row.needs_one_of and not (set(row.needs_one_of) & bundle_ids):
        return "needs a broadband or leased line in the same bundle"
    return None


def unlock_hint(reason: str) -> str:
    if "GSTIN" in reason:
        return "Register for GST free with a partner CA (Grow Ladder) — this unlocks in one tap"
    if "broadband" in reason:
        return "Add a broadband line to the bundle"
    if "employees" in reason or "sites" in reason:
        return "Becomes available as your business grows"
    return "We will notify you when it launches in your city"


def build_bundle(p: Profile, extra: list[str] | None = None, removed: list[str] | None = None) -> dict:
    """Pick products from needs, enforce every rule, and explain each decision."""
    cat = catalogue()
    wanted = set(SEGMENT_DEFAULT_NEEDS.get(p.segment, set())) | set(p.needs)
    ids: list[str] = []
    if "internet" in wanted or wanted & {"cctv", "wifi", "failover", "telephony", "firewall", "sdwan", "static_ip"}:
        ids.append(connectivity_choice(p))
    for need in sorted(wanted):
        pid = NEED_TO_PRODUCT.get(need)
        if pid and pid not in ids:
            ids.append(pid)
    for pid in extra or []:
        if pid in cat.index and pid not in ids:
            ids.append(pid)
    ids = [i for i in ids if i not in set(removed or [])]

    # Dependency pass: a product that needs broadband pulls in the right line if the
    # owner has not removed it on purpose.
    for pid in list(ids):
        deps = cat.loc[pid].needs_one_of
        if deps and not (set(deps) & set(ids)):
            line = connectivity_choice(p)
            if line in deps and line not in set(removed or []):
                ids.insert(0, line)

    items, withheld = [], []
    included: set[str] = set()
    for pid in ids:
        reason = check_item(pid, p, set(ids))
        if reason and pid == "P02" and "GSTIN" not in reason:
            pid = "P01"
            reason = check_item(pid, p, set(ids))
        if reason:
            withheld.append({"product_id": pid, "name": cat.loc[pid].product_name, "reason": reason,
                             "unlock": unlock_hint(reason)})
            continue
        included.add(pid)
        items.append({"product_id": pid, "name": cat.loc[pid].product_name, "category": cat.loc[pid].category,
                      "qty": default_qty(pid, p), "unit": cat.loc[pid].unit,
                      "unit_price": unit_price(pid, p), "setup": int(cat.loc[pid].one_time_setup_inr),
                      "install_days": int(cat.loc[pid].typical_install_days),
                      "why": PLAIN_WHY.get(pid, cat.loc[pid].description)})
    # Re-check dependencies after withholding (e.g. CCTV without a line).
    final = []
    for it in items:
        reason = check_item(it["product_id"], p, included)
        if reason:
            included.discard(it["product_id"])
            withheld.append({"product_id": it["product_id"], "name": it["name"], "reason": reason,
                             "unlock": unlock_hint(reason)})
        else:
            final.append(it)
    return {"items": final, "withheld": withheld}


def one_bill_discount(n_products: int) -> float:
    rate = 0.0
    for threshold, r in sorted(C.ONE_BILL_DISCOUNT.items()):
        if n_products >= threshold:
            rate = r
    return rate


def quote(p: Profile, bundle: dict, cluster_size: int = 0) -> dict:
    """Single transparent monthly price plus Ek Baithak's pricing ideas."""
    items = bundle["items"]
    monthly = sum(i["unit_price"] * i["qty"] for i in items)
    setup = sum(i["setup"] * (i["qty"] if i["setup"] else 0) for i in items)
    disc_rate = one_bill_discount(len(items))
    cluster_rate = C.BAZAAR_CLUSTER_DISCOUNT if cluster_size >= C.BAZAAR_CLUSTER_MIN_SHOPS else 0.0
    discount = round(monthly * (disc_rate + cluster_rate))
    net = monthly - discount
    gst = round(net * C.GST_RATE)
    setup_payable = 0 if p.contract_months >= 24 else setup

    # Bill-Swap mirror: the same services bought one by one (catalogue list price,
    # each with its own setup) versus one Accel bill.
    cat = catalogue()
    separate = sum(list_price(i["product_id"]) * i["qty"] for i in items) + round(setup / 12)
    vendors_replaced = len({i["category"] for i in items})

    # Switch Shield: owner is locked in elsewhere -> credit up to 2 months of the
    # old provider's monthly spend on the first Accel bill.
    shield = 0
    if p.locked_in and p.current_spend:
        shield = min(C.SWITCH_SHIELD_MAX_MONTHS * p.current_spend, C.SWITCH_SHIELD_CAP_INR)

    install_days = max([i["install_days"] for i in items] or [0])
    promise = C.TODAY + timedelta(days=install_days + 1)   # +1 day KYC, survey runs in parallel

    return {
        "monthly_list": monthly,
        "one_bill_discount_pct": round(disc_rate * 100),
        "bazaar_cluster_discount_pct": round(cluster_rate * 100),
        "discount": discount,
        "monthly_net": net,
        "gst": gst,
        "monthly_total_incl_gst": net + gst,
        "rozana_per_day": round(net / 30),                      # Rozana pricing
        "rozana_per_day_incl_gst": round((net + gst) / 30),
        "setup_fee": setup,
        "setup_payable": setup_payable,
        "setup_waived": setup_payable == 0 and setup > 0,
        "contract_months": p.contract_months,
        "bill_swap": {"separately_per_month": separate, "saving_per_month": max(0, separate - net),
                      "saving_pct": round(100 * max(0, separate - net) / separate) if separate else 0,
                      "vendors_replaced": vendors_replaced},
        "switch_shield_credit": shield,
        "promise_date": promise.isoformat(),
        "install_days": install_days,
    }


def grow_ladder_preview(p: Profile, bundle: dict) -> dict | None:
    """For a shop without GSTIN: what unlocks once GST registration is done."""
    if p.gstin_valid:
        return None
    locked = [w for w in bundle["withheld"] if "GSTIN" in w["reason"]]
    if not locked:
        return None
    upgraded = Profile(**{**p.__dict__, "gstin_valid": True})
    up_bundle = build_bundle(upgraded)
    return {"unlocks": [w["name"] for w in locked],
            "upgraded_monthly_net": quote(upgraded, up_bundle)["monthly_net"],
            "how": "A partner CA files your GST registration free; once the GSTIN is active, tap Upgrade."}
