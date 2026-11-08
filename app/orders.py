"""Consent ledger (DPDP Act 2023), orders, the tracker with promise-date credit,
Bazaar Clusters and Saathi attribution."""
from __future__ import annotations

from datetime import date, timedelta

from . import config as C
from . import store

PURPOSES = {
    "kyc": {"required": True, "en": "Verify your business documents (legal KYC for business connections)",
            "hi": "आपके बिज़नेस दस्तावेज़ों की जाँच (कानूनी KYC)"},
    "installation": {"required": True, "en": "Use your address to install and activate services",
                     "hi": "सेवा लगाने के लिए आपका पता इस्तेमाल करना"},
    "whatsapp_updates": {"required": False, "en": "Send order updates on WhatsApp", "hi": "WhatsApp पर ऑर्डर अपडेट"},
    "marketing": {"required": False, "en": "Send me offers (optional)", "hi": "ऑफ़र भेजें (वैकल्पिक)"},
}
RETENTION_TEXT = ("Document images: deleted 30 days after activation, or at once on rejection, abandonment or withdrawal. "
                  "Extracted fields: kept for the contract term plus the period telecom KYC and tax rules require.")


def record_consent(purposes: dict[str, bool], language: str) -> dict:
    missing = [p for p, meta in PURPOSES.items() if meta["required"] and not purposes.get(p)]
    if missing:
        raise ValueError(f"Required consent missing: {', '.join(missing)}")
    cid = store.new_id("CNS")
    entry = {"consent_id": cid, "purposes": {p: bool(purposes.get(p)) for p in PURPOSES},
             "language": language, "given_at": store.now(), "retention": RETENTION_TEXT, "withdrawn_at": None}
    store.put("consents", cid, entry)
    store.audit("consent.given", consent_id=cid, purposes=[p for p, v in entry["purposes"].items() if v])
    return entry


def withdraw_consent(cid: str) -> dict:
    entry = store.get("consents", cid)
    if not entry:
        raise KeyError(cid)
    entry["withdrawn_at"] = store.now()
    entry["purposes"] = {p: False for p in entry["purposes"]}
    store.put("consents", cid, entry)
    store.audit("consent.withdrawn", consent_id=cid, action="document images deleted, optional processing stopped")
    return entry


MILESTONES = [
    ("Order placed", 0), ("e-KYC verified & e-signed", 0), ("Site survey (booked at checkout)", 1),
    ("SIMs dispatched / eSIM live", 1),
]


def create_order(business_name: str, items: list[dict], quote: dict, consent_id: str,
                 saathi_code: str | None = None, cluster_code: str | None = None) -> dict:
    oid = store.new_id("EB")
    placed = C.TODAY
    timeline = [{"step": s, "due": (placed + timedelta(days=d)).isoformat()} for s, d in MILESTONES]
    for it in sorted(items, key=lambda i: i["install_days"]):
        timeline.append({"step": f"{it['name']} live", "due": (placed + timedelta(days=it['install_days'] + 1)).isoformat()})
    order = {"order_id": oid, "business_name": business_name, "placed_on": placed.isoformat(),
             "promise_date": quote["promise_date"], "monthly_net": quote["monthly_net"],
             "items": [{"product_id": i["product_id"], "name": i["name"], "qty": i["qty"]} for i in items],
             "timeline": timeline, "consent_id": consent_id, "saathi_code": saathi_code,
             "cluster_code": cluster_code, "switch_shield_credit": quote.get("switch_shield_credit", 0)}
    store.put("orders", oid, order)
    store.audit("order.created", order_id=oid, saathi=saathi_code, cluster=cluster_code)
    if saathi_code:
        commission = round(quote["monthly_net"] * 12 * C.SAATHI_COMMISSION)
        store.put("commissions", oid, {"saathi_code": saathi_code, "order_id": oid, "commission_inr": commission})
    return order


def track(oid: str, as_of: date | None = None, delay_days: int = 0) -> dict:
    """Status view the owner checks instead of calling support. `delay_days`
    simulates an install crew slipping, to show the automatic late-day credit."""
    order = store.get("orders", oid)
    if not order:
        raise KeyError(oid)
    today = as_of or C.TODAY + timedelta(days=2)
    steps = []
    for s in order["timeline"]:
        planned = date.fromisoformat(s["due"])
        actual = planned + timedelta(days=delay_days) if s["step"].endswith(" live") else planned
        steps.append({"step": s["step"], "due": actual.isoformat(), "planned": s["due"], "done": actual <= today})
    promise = date.fromisoformat(order["promise_date"])
    live_on = max(date.fromisoformat(s["due"]) for s in steps)
    late_days = max(0, (min(today, live_on) - promise).days)
    credit = round(order["monthly_net"] * C.LATE_DAY_CREDIT_SHARE * late_days)
    if all(s["done"] for s in steps):
        status = "Live" if not late_days else f"Live — {late_days} day(s) late, credit applied"
    else:
        status = "Late — credit running" if late_days else "On track"
    return {**order, "as_of": today.isoformat(), "steps": steps, "status": status,
            "late_days": late_days, "late_credit_inr": credit}


def join_cluster(code: str, business_name: str) -> dict:
    """Bazaar Cluster: shops in one market lane sign together for a group price."""
    code = code.strip().upper()
    c = store.get("clusters", code) or {"code": code, "members": []}
    if business_name and business_name not in c["members"]:
        c["members"].append(business_name)
    store.put("clusters", code, c)
    size = len(c["members"])
    return {"code": code, "size": size, "unlocked": size >= C.BAZAAR_CLUSTER_MIN_SHOPS,
            "needed": max(0, C.BAZAAR_CLUSTER_MIN_SHOPS - size),
            "discount_pct": round(C.BAZAAR_CLUSTER_DISCOUNT * 100)}
