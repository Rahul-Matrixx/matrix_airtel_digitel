"""Smart KYC: multi-pass OCR, field extraction and cross-document validation.

Pipeline per document: quality score -> clean-up passes (de-watermark, deskew,
sharpen) -> best OCR pass -> field parser. Then registry + cross-document checks
produce APPROVED / NEEDS_REVIEW / REJECTED, each with plain reasons.
Images are processed in memory and never written to disk.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime
from difflib import SequenceMatcher

import cv2
import numpy as np
import pytesseract
from PIL import Image

from . import config as C
from .registry import lookup_gstin, lookup_udyam, mask, normalize_udyam, repair_gstin, validate_gstin

DOC_TYPES = ["gst_certificate", "udyam_certificate", "signatory_id", "address_proof"]
LABELS = {
    "gst_certificate": ["gstin", "legal name", "trade name", "constitution", "address"],
    "udyam_certificate": ["udyam", "enterprise name", "city", "state"],
    "signatory_id": ["name", "designation", "valid till", "id no"],
    "address_proof": ["billed to", "supply address", "bill date"],
}


# ---------------------------------------------------------------- image passes
def _gray(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def blur_score(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def dewatermark(gray: np.ndarray) -> np.ndarray:
    """Light grey watermarks sit well above text darkness: push them to white."""
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return th


def skew_angle(gray: np.ndarray) -> float:
    """Projection-profile search over ±8°, on a downscaled binarised copy."""
    small = cv2.resize(gray, None, fx=0.35, fy=0.35)
    inv = 255 - cv2.threshold(small, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    best, best_score = 0.0, -1.0
    h, w = inv.shape
    for ang in np.arange(-8, 8.25, 0.5):
        M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
        rot = cv2.warpAffine(inv, M, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        score = float(np.var(rot.sum(axis=1)))
        if score > best_score:
            best, best_score = float(ang), score
    return best


def rotate(gray: np.ndarray, angle: float) -> np.ndarray:
    h, w = gray.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderValue=255)


def sharpen(gray: np.ndarray) -> np.ndarray:
    up = cv2.resize(gray, None, fx=1.6, fy=1.6, interpolation=cv2.INTER_CUBIC)
    blur = cv2.GaussianBlur(up, (0, 0), 3)
    return cv2.addWeighted(up, 1.8, blur, -0.8, 0)


def ocr_best(image_bytes: bytes, doc_type: str) -> dict:
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Unreadable image")
    gray = _gray(img)
    quality = {"blur_score": round(blur_score(gray), 1), "skew_deg": 0.0}
    angle = skew_angle(gray)
    quality["skew_deg"] = angle
    passes = [("original", gray), ("dewatermark", dewatermark(gray))]
    if abs(angle) >= 0.5:
        straight = rotate(gray, angle)
        passes += [("deskew", straight), ("deskew+dewatermark", dewatermark(straight))]
    if quality["blur_score"] < 150:
        base = passes[-1][1]
        passes += [("sharpen", sharpen(base)), ("sharpen+threshold", dewatermark(sharpen(base)))]
    best = {"score": -1}
    for name, p in passes:
        text = pytesseract.image_to_string(Image.fromarray(p), config="--psm 6")
        low = text.lower()
        score = sum(lbl in low for lbl in LABELS[doc_type]) + len(re.findall(r"\d{4}-\d{2}-\d{2}", text)) * 0.2
        if score > best["score"]:
            best = {"score": score, "pass": name, "text": text}
    best["quality"] = quality
    return best


# ---------------------------------------------------------------- field parsers
def _after(label: str, text: str) -> str | None:
    m = re.search(rf"{label}\s*[:\-]?\s*(.+)", text, re.I)
    return m.group(1).strip() if m and m.group(1).strip() else None


def _next_line(label: str, lines: list[str]) -> str | None:
    for i, ln in enumerate(lines):
        if re.fullmatch(rf"\s*{label}\s*[:]?\s*", ln, re.I):
            for nxt in lines[i + 1:]:
                if nxt.strip():
                    return nxt.strip()
        if m := re.match(rf"\s*{label}\s*[:\-]?\s+(.+)", ln, re.I):
            return m.group(1).strip()
    return None


def _date(s: str | None) -> date | None:
    if not s:
        return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s.replace(" ", ""))
    if not m:
        return None
    try:
        return datetime.strptime(m.group(0), "%Y-%m-%d").date()
    except ValueError:
        return None


def _joined_address(label: str, text: str) -> str | None:
    """Addresses wrap onto a second line in the specimens; re-join them."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    stop = re.compile(r"^\s*(bill date|date of|type of|units|amount|consumer|accel|gstin|legal|trade|constitution)", re.I)
    for i, ln in enumerate(lines):
        if re.match(rf"\s*{label}", ln, re.I):
            out = re.sub(rf"^\s*{label}\s*", "", ln, flags=re.I)
            if not re.search(r"\d{6}", out) and i + 1 < len(lines) and not stop.match(lines[i + 1]):
                nxt = re.sub(r"^\s*(place of business|of business)\s*", "", lines[i + 1], flags=re.I)
                out = out + nxt
            return re.sub(r"\s+", " ", out.replace("--", "-")).strip()
    return None


def parse(doc_type: str, text: str) -> dict:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if doc_type == "gst_certificate":
        g = re.search(r"GSTIN\s*[:\-]?\s*([0-9A-Z]{15})", text.replace(" ", "").replace("GSTIN", "GSTIN "), re.I)
        if not g:
            g = re.search(r"\b([0-9O]{2}[A-Z0-9]{13})\b", text)
        return {"gstin": g.group(1) if g else None, "legal_name": _after("Legal name", text),
                "trade_name": _after("Trade name", text), "constitution": _after("Constitution", text),
                "address": _joined_address("Address of principal", text)}
    if doc_type == "udyam_certificate":
        u = re.search(r"UDYAM\s*[-—–]?\s*[A-Z0-9]{2}\s*[-—–]?\s*[0-9O]{2}\s*[-—–]?\s*[0-9O]{7}", text, re.I)
        return {"udyam_number": normalize_udyam(u.group(0)) if u else None,
                "enterprise_name": _after("Enterprise name", text), "city": _after("City", text),
                "state": _after("State", text)}
    if doc_type == "signatory_id":
        return {"name": _next_line("Name", lines), "designation": _next_line("Designation", lines),
                "for_business": _next_line("For business", lines), "id_no": _next_line("ID no\\.?", lines),
                "valid_till": (_date(_next_line("Valid till", lines)) or None)}
    if doc_type == "address_proof":
        return {"billed_to": _after("Billed to", text), "address": _joined_address("Supply address", text),
                "bill_date": _date(_after("Bill date", text))}
    return {}


# ---------------------------------------------------------------- validation
def _norm_name(s: str | None) -> str:
    s = (s or "").lower()
    s = re.sub(r"\(prop\.?\s*", " ", s)
    s = re.sub(r"\b(pvt|private|ltd|limited|llp|m/s|prop)\b\.?", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def same_name(a: str | None, b: str | None, threshold: float = 0.93) -> bool:
    """Strict: tolerate OCR noise (punctuation, a stray letter) but not a changed word."""
    if not a or not b:
        return False
    x, y = _norm_name(a), _norm_name(b)
    if x == y or set(x.split()) == set(y.split()):
        return True
    if (x in y or y in x) and min(len(x), len(y)) >= 8:
        return True
    return SequenceMatcher(None, x, y).ratio() >= threshold


def _pin(s: str | None) -> str | None:
    m = re.search(r"(\d{6})\b", (s or "").replace(" ", ""))
    return m.group(1) if m else None


def verify(docs: dict[str, bytes]) -> dict:
    """docs: {doc_type: image bytes}. Returns verdict, checks and masked fields."""
    checks: list[dict] = []
    extracted: dict[str, dict] = {}
    passes: dict[str, dict] = {}

    def add(name: str, ok: bool, severity: str, detail: str):
        checks.append({"check": name, "ok": ok, "severity": "ok" if ok else severity, "detail": detail})

    for dt in DOC_TYPES:
        if dt not in docs:
            add(f"{dt.replace('_', ' ')} uploaded", False, "review",
                f"Missing {dt.replace('_', ' ')} — ask the owner to upload it or pull it from DigiLocker")
            continue
        ocr = ocr_best(docs[dt], dt)
        f = parse(dt, ocr["text"])
        extracted[dt] = f
        passes[dt] = {"pass": ocr["pass"], **ocr["quality"]}
        needed = [k for k in f if k not in ("address", "constitution", "for_business", "id_no", "city", "state")]
        missing = [k for k in needed if not f.get(k)]
        blank = [k for k in missing if k == "udyam_number" and "udyam reg" in ocr["text"].lower()]
        if blank and ocr["quality"]["blur_score"] >= 150:
            add("udyam number present", False, "reject", "Udyam registration number is blank on the certificate")
            missing = [k for k in missing if k not in blank]
        if missing:
            q = ocr["quality"]
            why = ("photo is blurred" if q["blur_score"] < 150 else
                   f"photo is tilted {abs(q['skew_deg']):.1f}°" if abs(q["skew_deg"]) >= 3 else "fields unreadable")
            add(f"{dt.replace('_', ' ')} readable", False, "review",
                f"Could not read {', '.join(missing)} ({why}) — ask for a clearer photo or DigiLocker copy")
        else:
            add(f"{dt.replace('_', ' ')} readable", True, "ok", f"read via '{ocr['pass']}' pass")

    gst, udy = extracted.get("gst_certificate", {}), extracted.get("udyam_certificate", {})
    sig, bill = extracted.get("signatory_id", {}), extracted.get("address_proof", {})
    reg = None
    if gst.get("gstin"):
        fix = repair_gstin(gst["gstin"], gst.get("legal_name"))
        if fix["repaired"]:
            add("GSTIN OCR auto-corrected", True, "ok", "look-alike characters fixed using the check digit + registry")
        gst["gstin"] = fix["gstin"]
        v = validate_gstin(gst["gstin"])
        add("GSTIN format + check digit", v["format_ok"] and v["checksum_ok"], "reject",
            "valid structure and mod-36 check digit" if v["checksum_ok"] else "; ".join(v["issues"]))
        reg = lookup_gstin(v["gstin"])
        if reg is None:
            add("GSTIN found in registry", False, "reject", "GSTIN not found in the GST registry")
        else:
            status = reg["status"]
            add("GSTIN status active", status == "Active", "reject", f"registry status: {status}")
            add("Legal name matches registry", same_name(gst.get("legal_name"), reg["legal_name"]), "reject",
                "certificate legal name matches the registry" if same_name(gst.get("legal_name"), reg["legal_name"])
                else "legal name on the certificate differs from the GST registry — possible tampering")
            add("Trade name matches registry", same_name(gst.get("trade_name"), reg["trade_name"]), "reject",
                "trade name matches" if same_name(gst.get("trade_name"), reg["trade_name"])
                else "trade name differs from the GST registry")
    business = (reg or {}).get("trade_name") or gst.get("trade_name") or udy.get("enterprise_name")
    business_alt = (reg or {}).get("legal_name") or gst.get("legal_name")

    if udy.get("udyam_number"):
        ur = lookup_udyam(udy["udyam_number"])
        add("Udyam found in registry", ur is not None, "reject",
            "Udyam number found" if ur else "Udyam number not in the registry")
        if ur:
            ok = same_name(ur["enterprise_name"], business) or same_name(ur["enterprise_name"], business_alt)
            add("Udyam name matches business", ok, "reject",
                "enterprise name matches GST" if ok else "Udyam enterprise name differs from the GST record")
            if reg:
                add("Udyam state matches GST state", ur["state"] == reg["state"], "review",
                    f"{ur['state']} vs {reg['state']}")

    if bill:
        bd = bill.get("bill_date")
        if bd:
            age = (C.TODAY - bd).days
            add("Address proof ≤ 90 days old", age <= 90, "reject", f"bill dated {bd.isoformat()} ({age} days old)")
        ok = same_name(bill.get("billed_to"), business) or same_name(bill.get("billed_to"), business_alt)
        add("Bill is in the business's name", ok, "review", "billed-to name matches" if ok else "billed-to name differs")
        ref_addr = (reg or {}).get("principal_place_of_business") or gst.get("address")
        pin_bill, pin_ref = _pin(bill.get("address")), _pin(ref_addr)
        if pin_bill and pin_ref:
            add("Bill PIN matches GST address", pin_bill == pin_ref, "review", f"{pin_bill} vs {pin_ref}")

    if sig:
        vt = sig.get("valid_till")
        if vt:
            add("Signatory ID not expired", vt >= C.TODAY, "reject", f"valid till {vt.isoformat()}")
        if sig.get("for_business"):
            ok = same_name(sig["for_business"], business) or same_name(sig["for_business"], business_alt)
            add("Signatory ID is for this business", ok, "reject", "matches" if ok else "ID issued for a different business")
        role = (sig.get("designation") or "").lower()
        constitution = ((reg or {}).get("constitution") or gst.get("constitution") or "").lower()
        if not constitution:   # GST page unreadable: infer from the name on other documents
            hint = " ".join(filter(None, [udy.get("enterprise_name"), bill.get("billed_to"), sig.get("for_business")])).lower()
            constitution = ("limited liability partnership" if re.search(r"\bllp\b", hint) else
                            "private limited company" if re.search(r"pvt|private|limited|ltd", hint) else "")
        legal = (reg or {}).get("legal_name") or gst.get("legal_name") or ""
        prop = re.search(r"^(.+?)\s*\(prop", legal, re.I)
        if "proprietor" in constitution:
            authorised = bool(prop and same_name(prop.group(1), sig.get("name")))
            need = "only the proprietor named on the GST record can sign"
        elif "liability partnership" in constitution or constitution.startswith("llp"):
            authorised = "partner" in role
            need = "an LLP must be signed by a designated partner"
        elif "partnership" in constitution:
            authorised = "partner" in role
            need = "a partnership must be signed by a partner"
        elif not constitution:
            authorised = False
            need = "business type unknown until the GST certificate is readable"
        else:
            authorised = any(r in role for r in ("director", "authorised signatory", "authorized signatory", "managing"))
            need = "a company must be signed by a director or board-authorised signatory"
        add("Signatory has authority to sign", authorised, "review",
            f"{sig.get('name')} ({sig.get('designation')}) for a {constitution or 'business'}"
            + ("" if authorised else f" — {need}; ask for an authorisation letter"))
        if abs(passes.get("gst_certificate", {}).get("skew_deg", 0)) >= 3:
            add("Tilted photo straightened", True, "ok", f"GST certificate was tilted {abs(passes['gst_certificate']['skew_deg']):.1f}° and auto-straightened")

    if any(c["severity"] == "reject" for c in checks):
        verdict = "REJECTED"
    elif any(c["severity"] == "review" for c in checks):
        verdict = "NEEDS_REVIEW"
    else:
        verdict = "APPROVED"

    masked = {}
    for dt, f in extracted.items():
        masked[dt] = {k: (mask(v) if k in ("gstin", "udyam_number", "id_no") else
                          (v.isoformat() if isinstance(v, date) else v)) for k, v in f.items()}
    return {"verdict": verdict, "reasons": [c["detail"] for c in checks if not c["ok"]],
            "checks": checks, "fields": masked, "ocr": passes}


def load_specimen(applicant: str) -> dict[str, bytes]:
    folder = C.DATA_DIR / "kyc_documents"
    out = {}
    for dt in DOC_TYPES:
        p = folder / f"{applicant}_{dt}.png"
        if p.exists():
            out[dt] = p.read_bytes()
    return out
