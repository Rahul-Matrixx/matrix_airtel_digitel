"""GSTIN / Udyam validation, mock registry lookups and identifier masking."""
from __future__ import annotations

import re
from functools import lru_cache

import pandas as pd

from .config import DATA_DIR

CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")

STATE_CODES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "18": "Assam", "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat", "27": "Maharashtra",
    "29": "Karnataka", "30": "Goa", "32": "Kerala", "33": "Tamil Nadu", "36": "Telangana",
    "37": "Andhra Pradesh",
}


def gstin_check_char(first14: str) -> str:
    """Official GSTIN check digit: base-36, alternating weights 1 and 2."""
    total = 0
    for i, ch in enumerate(first14):
        product = CHARSET.index(ch) * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return CHARSET[(36 - total % 36) % 36]


def normalize_gstin(raw: str) -> str:
    """Fix common OCR confusions using the GSTIN grammar (digits vs letters by position)."""
    s = re.sub(r"[^0-9A-Za-z]", "", raw or "").upper()
    if len(s) != 15:
        return s
    digit_pos = {0, 1, 7, 8, 9, 10}
    letter_pos = {2, 3, 4, 5, 6, 11}
    to_digit = {"O": "0", "D": "0", "Q": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8", "G": "6"}
    to_letter = {v: k for k, v in {"O": "0", "I": "1", "Z": "2", "S": "5", "B": "8", "G": "6"}.items()}
    chars = list(s)
    for i, c in enumerate(chars):
        if i in digit_pos and not c.isdigit():
            chars[i] = to_digit.get(c, c)
        elif i in letter_pos and c.isdigit():
            chars[i] = to_letter.get(c, c)
    if chars[13] != "Z":
        chars[13] = "Z" if chars[13] in "2" else chars[13]
    return "".join(chars)


def validate_gstin(raw: str) -> dict:
    g = normalize_gstin(raw)
    result = {"gstin": g, "format_ok": bool(GSTIN_RE.match(g)), "checksum_ok": False, "state": None, "issues": []}
    if not result["format_ok"]:
        result["issues"].append("GSTIN does not follow the 15-character structure")
        return result
    result["checksum_ok"] = gstin_check_char(g[:14]) == g[14]
    if not result["checksum_ok"]:
        result["issues"].append("GSTIN check digit is wrong (typo or tampered number)")
    result["state"] = STATE_CODES.get(g[:2])
    return result


def normalize_udyam(raw: str) -> str:
    s = re.sub(r"\s+", "", (raw or "").upper()).replace("—", "-").replace("–", "-")
    m = re.search(r"UDYAM-?([A-Z0-9]{2})-?([0-9O]{2})-?([0-9O]{7})", s)
    if not m:
        return s
    state = m.group(1).replace("0", "O").replace("1", "I")
    return f"UDYAM-{state}-{m.group(2).replace('O', '0')}-{m.group(3).replace('O', '0')}"


@lru_cache(maxsize=1)
def _gst_table() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "mock_gstin_registry.csv", dtype=str).set_index("gstin")


@lru_cache(maxsize=1)
def _udyam_table() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "mock_udyam_registry.csv", dtype=str).set_index("udyam_number")


def lookup_gstin(gstin: str) -> dict | None:
    g = normalize_gstin(gstin)
    t = _gst_table()
    if g not in t.index:
        return None
    row = t.loc[g].to_dict()
    row["gstin"] = g
    return row


def lookup_udyam(number: str) -> dict | None:
    u = normalize_udyam(number)
    t = _udyam_table()
    if u not in t.index:
        return None
    row = t.loc[u].to_dict()
    row["udyam_number"] = u
    return row


def mask(identifier: str | None, keep_start: int = 2, keep_end: int = 3) -> str:
    """37IHKXV5167L1ZS -> 37••••••••••1ZS. Used in UI, API responses and logs."""
    if not identifier:
        return ""
    s = str(identifier)
    if len(s) <= keep_start + keep_end:
        return "•" * len(s)
    return s[:keep_start] + "•" * (len(s) - keep_start - keep_end) + s[-keep_end:]


CONFUSABLE = {
    "0": "ODQ", "O": "0DQ", "D": "0O", "Q": "0O", "1": "ILTJ", "I": "1LTJ", "L": "1I", "T": "I1J", "J": "I1T",
    "5": "S68", "S": "58", "8": "B53", "B": "8", "3": "8", "2": "Z", "Z": "2", "6": "G58", "G": "6",
    "U": "VW", "V": "UY", "Y": "V", "W": "U", "K": "X", "X": "K", "M": "N", "N": "M", "E": "F", "F": "E", "C": "G",
}


def repair_gstin(raw: str, name_hint: str | None = None) -> dict:
    """If OCR broke the check digit, try 1-2 look-alike swaps; accept only a
    candidate that passes the checksum AND exists in the registry."""
    g = normalize_gstin(raw)
    v = validate_gstin(g)
    if v["checksum_ok"] or len(g) != 15:
        return {"gstin": g, "repaired": False, "candidates": 0}
    from itertools import combinations
    hits = []
    positions = range(15)
    for pos in positions:
        for alt in CONFUSABLE.get(g[pos], ""):
            c = g[:pos] + alt + g[pos + 1:]
            if validate_gstin(c)["checksum_ok"] and lookup_gstin(c):
                hits.append(normalize_gstin(c))
    if not hits:
        for a, b in combinations(positions, 2):
            for x in CONFUSABLE.get(g[a], ""):
                for y in CONFUSABLE.get(g[b], ""):
                    c = list(g); c[a], c[b] = x, y; c = "".join(c)
                    if validate_gstin(c)["checksum_ok"] and lookup_gstin(c):
                        hits.append(normalize_gstin(c))
    hits = sorted(set(hits))
    if len(hits) > 1 and name_hint:
        key = re.sub(r"[^a-z0-9]", "", name_hint.lower())
        named = [h for h in hits if key in {re.sub(r"[^a-z0-9]", "", str(lookup_gstin(h)[f]).lower())
                                              for f in ("legal_name", "trade_name")}]
        hits = named or hits
    if len(hits) == 1:
        return {"gstin": hits[0], "repaired": True, "candidates": 1}
    return {"gstin": g, "repaired": False, "candidates": len(hits)}
