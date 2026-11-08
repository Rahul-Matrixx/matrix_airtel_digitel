"""Conversational advisor: understands taps or one free-text sentence (English,
Hindi, Hinglish), turns it into a Profile, and explains the bundle in plain words.

The parser is deterministic. An optional LLM (set ANTHROPIC_API_KEY) may only
rephrase the explanation text; it never sees identifiers and cannot change items.
"""
from __future__ import annotations

import json
import os
import re

from .catalogue import Profile, city_tiers

TYPE_KEYWORDS = [
    # (keywords, business_type, segment)
    (["kirana", "general store", "grocery", "किराना", "दुकान", "dukaan", "dukan", "shop"], "Kirana / general store", "micro"),
    (["salon", "parlour", "parlor", "सैलून"], "Salon", "micro"),
    (["pharmacy", "medical store", "chemist", "दवाई", "medical shop"], "Pharmacy", "micro"),
    (["bakery", "sweet", "mithai"], "Bakery / sweets", "micro"),
    (["clinic", "doctor", "dental", "physio", "क्लिनिक", "hospital"], "Clinic", "prof"),
    (["ca firm", "chartered", "accountant", " ca ", "tax consultant"], "CA firm", "prof"),
    (["coaching", "tuition", "institute", "classes", "कोचिंग"], "Coaching centre", "prof"),
    (["office", "agency", "consult", "realty", "travels", "law"], "Professional office", "prof"),
    (["restaurant", "cafe", "café", "dhaba", "hotel", "रेस्टोरेंट"], "Restaurant", "multi"),
    (["chain", "outlets", "branches", "stores", "showrooms"], "Multi-site chain", "multi"),
    (["factory", "manufactur", "plant", "textile", "auto parts", "auto-parts", "फैक्ट्री", "workshop", "mill"], "Manufacturing unit", "mfg"),
]

NEED_KEYWORDS = {
    "internet": ["internet", "net", "wifi chahiye", "broadband", "fibre", "fiber", "इंटरनेट"],
    "upi": ["upi", "qr", "payment"],
    "pos": ["pos", "billing", "bill machine", "बिलिंग", "invoice"],
    "cctv": ["cctv", "camera", "सीसीटीवी", "कैमरा"],
    "whatsapp": ["whatsapp", "व्हाट्सएप", "catalogue"],
    "sms": ["sms", "message blast"],
    "email": ["email", "mail", "ईमेल"],
    "backup": ["backup", "storage", "data safe"],
    "wifi": ["wifi", "wi-fi", "guest", "वाईफाई"],
    "antivirus": ["antivirus", "virus", "ransomware"],
    "firewall": ["firewall", "security", "hack"],
    "iot": ["sensor", "machine", "iot", "energy"],
    "fleet": ["gps", "fleet", "vehicle", "gaadi", "truck", "delivery bike"],
    "telephony": ["ivr", "call centre", "phone line", "landline"],
    "tollfree": ["toll free", "toll-free", "1800"],
    "website": ["website", "site banana", "online dukaan"],
    "sim": ["sim", "mobile", "सिम"],
    "failover": ["backup line", "never down", "failover", "net band"],
}

STAFF_RE = re.compile(r"(\d+)\s*(?:log|logo|people|staff|employees|employee|workers|लोग|कर्मचारी|jan|members)", re.I)
SITE_RE = re.compile(r"(\d+)\s*(?:shops|outlets|branches|sites|stores|dukaan|dukane|locations|शाखा|दुकानें)", re.I)
CAM_RE = re.compile(r"(\d+)\s*(?:camera|cameras|cctv)", re.I)
SIM_RE = re.compile(r"(\d+)\s*(?:sim|sims|lines|सिम)", re.I)

QUESTIONS = [
    {"id": "business", "en": "What kind of business is it?", "hi": "आपका बिज़नेस किस तरह का है?",
     "chips": ["Kirana / shop", "Salon", "Pharmacy", "Clinic", "CA firm", "Coaching", "Restaurant", "Store chain", "Factory"]},
    {"id": "employees", "en": "How many people work there?", "hi": "कितने लोग काम करते हैं?", "chips": ["1-2", "3-9", "10-24", "25+"]},
    {"id": "sites", "en": "How many shops or branches?", "hi": "कितनी दुकानें / ब्रांच हैं?", "chips": ["1", "2", "3-4", "5+"]},
    {"id": "city", "en": "Which city?", "hi": "आप किस शहर में हैं?", "chips": ["Pune", "Jaipur", "Delhi", "Mumbai", "Chennai", "Kochi"]},
    {"id": "needs", "en": "What do you need? (tap all)", "hi": "आपको क्या चाहिए? (सब चुनें)",
     "chips": ["Internet", "UPI / billing", "CCTV", "WhatsApp", "Email", "Wi-Fi for customers", "Backup"]},
    {"id": "gstin", "en": "Your GST number (optional — skip if none)", "hi": "आपका GST नंबर (ना हो तो छोड़ दें)", "chips": ["I don't have GST"]},
]

CHIP_TO_TYPE = {"Kirana / shop": "kirana", "Salon": "salon", "Pharmacy": "pharmacy", "Clinic": "clinic",
                "CA firm": "ca firm", "Coaching": "coaching", "Restaurant": "restaurant",
                "Store chain": "chain", "Factory": "factory"}
CHIP_TO_NEED = {"Internet": "internet", "UPI / billing": "pos", "CCTV": "cctv", "WhatsApp": "whatsapp",
                "Email": "email", "Wi-Fi for customers": "wifi", "Backup": "backup"}
CHIP_TO_NUM = {"1-2": 2, "3-9": 5, "10-24": 15, "25+": 30, "1": 1, "2": 2, "3-4": 3, "5+": 5}


def parse_free_text(text: str) -> dict:
    """'kirana hai, 3 log, UPI aur CCTV chahiye, Jaipur' -> structured profile fields."""
    t = f" {text.lower()} "
    out: dict = {"needs": set()}
    for kws, btype, seg in TYPE_KEYWORDS:
        if any(k in t for k in kws):
            out.setdefault("business_type", btype)
            out.setdefault("segment", seg)
    if m := STAFF_RE.search(t):
        out["employees"] = int(m.group(1))
    if m := SITE_RE.search(t):
        out["sites"] = int(m.group(1))
        if out["sites"] >= 2 and out.get("segment") == "micro":
            out["segment"] = "multi"
    if m := CAM_RE.search(t):
        out["cameras"] = int(m.group(1))
    if m := SIM_RE.search(t):
        out["sim_lines"] = int(m.group(1))
    for need, kws in NEED_KEYWORDS.items():
        if any(k in t for k in kws):
            out["needs"].add(need)
    for city in city_tiers():
        if city.lower() in t:
            out["city"] = city
            break
    if any(k in t for k in ["contract", "lock", "locked", "bandh", "agreement"]):
        out["locked_in"] = True
    if m := re.search(r"(?:₹|\brs\.?|\binr)\s*(\d[\d,]*)", t):
        out["current_spend"] = int(m.group(1).replace(",", ""))
    if re.search(r"[ऀ-ॿ]", text) or any(w in t for w in [" hai", " chahiye", " aur ", " log"]):
        out["language"] = "hi"
    return out


def profile_from(answers: dict) -> Profile:
    """Merge chip answers and/or a parsed sentence into a Profile."""
    data = {}
    if answers.get("text"):
        data.update(parse_free_text(answers["text"]))
    if answers.get("business"):
        data.update({k: v for k, v in parse_free_text(CHIP_TO_TYPE.get(answers["business"], answers["business"])).items() if k in ("business_type", "segment")})
    for key in ("employees", "sites"):
        if answers.get(key):
            v = answers[key]
            data[key] = CHIP_TO_NUM.get(str(v), int(v) if str(v).isdigit() else 1)
    if answers.get("city"):
        data["city"] = answers["city"]
    needs = set(data.get("needs", set()))
    for chip in answers.get("needs", []) or []:
        needs.add(CHIP_TO_NEED.get(chip, chip))
    data["needs"] = needs
    for key in ("locked_in", "current_spend", "contract_months", "cluster_code", "language", "sim_lines", "cameras"):
        if answers.get(key) not in (None, ""):
            data[key] = answers[key]
    data.setdefault("segment", "micro")
    if data.get("sites", 1) >= 2 and data["segment"] == "micro":
        data["segment"] = "multi"
    data["city_tier"] = city_tiers().get(data.get("city", ""), 2)
    fields = Profile.__dataclass_fields__
    return Profile(**{k: v for k, v in data.items() if k in fields})


HI_WHY = {
    "P01": "तेज़ फाइबर इंटरनेट — UPI, बिलिंग और वीडियो कॉल के लिए", "P02": "और तेज़ फाइबर, ताकि कई लोग एक साथ काम कर सकें",
    "P04": "5G वायरलेस इंटरनेट — बिना खुदाई, 2 दिन में चालू", "P07": "बिज़नेस सिम — 50 GB डेटा, अनलिमिटेड कॉल",
    "P19": "GST बिलिंग मशीन — UPI और कार्ड पेमेंट", "P15": "वेरिफाइड WhatsApp चैनल, आपके कैटलॉग के साथ",
    "P23": "HD कैमरा — 30 दिन की रिकॉर्डिंग, मोबाइल पर देखें", "P22": "सुरक्षित Wi-Fi, ग्राहकों के लिए अलग नेटवर्क",
    "P16": "आपके नाम का ईमेल, डॉक्यूमेंट और वीडियो मीटिंग", "P17": "PC और फ़ोन का अपने-आप बैकअप",
    "P20": "वायरस और रैनसमवेयर से सुरक्षा", "P09": "मेन लाइन बंद हो तो बैकअप राउटर से इंटरनेट चालू",
}


def explain(profile: Profile, bundle: dict, q: dict) -> list[str]:
    """Deterministic plain-language explanation; one line per decision."""
    hi = profile.language == "hi"
    lines = []
    for it in bundle["items"]:
        why = HI_WHY.get(it["product_id"]) if hi else None
        lines.append(f"{it['name']} ×{it['qty']}: {why or it['why']}.")
    for w in bundle["withheld"]:
        lines.append(f"Not included — {w['name']}: {w['reason']}. {w['unlock']}.")
    lines.append(f"About ₹{q['rozana_per_day']}/day (₹{q['monthly_net']:,}/month + GST)."
                 if not hi else f"लगभग ₹{q['rozana_per_day']} रोज़ (₹{q['monthly_net']:,} महीना + GST)।")
    return lines


def llm_rephrase(lines: list[str], language: str) -> list[str]:
    """Optional: let an LLM make the explanation friendlier. Falls back silently."""
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return lines
    try:
        import httpx
        prompt = ("Rephrase these lines for a small shop owner in "
                  f"{'simple Hindi' if language == 'hi' else 'simple English'}. Keep every product, number and price "
                  "exactly as given. Do not add or remove products. Return a JSON list of strings.\n" + json.dumps(lines))
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=15,
                       headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                       json={"model": os.getenv("LLM_MODEL", "claude-haiku-5-5"), "max_tokens": 800,
                             "messages": [{"role": "user", "content": prompt}]})
        out = json.loads(r.json()["content"][0]["text"])
        return out if isinstance(out, list) and len(out) == len(lines) else lines
    except Exception:
        return lines
