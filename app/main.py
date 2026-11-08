"""Ek Baithak API — Team Matrix. Run: uvicorn app.main:app --reload"""
from __future__ import annotations

import warnings

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import advisor, catalogue, kyc, orders, propensity, registry, store
from .config import WEB_DIR

warnings.filterwarnings("ignore", category=UserWarning)

app = FastAPI(title="Ek Baithak API", version="1.0", description="Digital in one sitting — Team Matrix")


class AdviseIn(BaseModel):
    text: str | None = Field(None, examples=["kirana hai, 3 log, UPI aur CCTV chahiye, Jaipur"])
    business: str | None = None
    employees: str | int | None = None
    sites: str | int | None = None
    city: str | None = None
    needs: list[str] = []
    gstin: str | None = None
    locked_in: bool = False
    current_spend: int | None = None
    contract_months: int = 12
    cluster_code: str | None = None
    language: str | None = None
    add: list[str] = []
    remove: list[str] = []
    business_name: str | None = None


def _gstin_status(raw: str | None) -> dict:
    if not raw:
        return {"provided": False, "valid": False}
    v = registry.validate_gstin(raw)
    rec = registry.lookup_gstin(v["gstin"]) if v["checksum_ok"] else None
    out = {"provided": True, "masked": registry.mask(v["gstin"]), "format_ok": v["format_ok"],
           "checksum_ok": v["checksum_ok"], "found": rec is not None,
           "status": rec["status"] if rec else None, "valid": bool(rec and rec["status"] == "Active"),
           "issues": v["issues"]}
    if rec:
        out.update({"trade_name": rec["trade_name"], "state": rec["state"],
                    "constitution": rec["constitution"]})
    store.audit("gstin.lookup", gstin=registry.mask(v["gstin"]), found=out["found"], status=out["status"])
    return out


@app.post("/api/advise")
def advise(body: AdviseIn):
    """Profile -> eligible bundle -> one transparent price, explained in plain words."""
    answers = body.model_dump()
    p = advisor.profile_from(answers)
    g = _gstin_status(body.gstin)
    p.gstin_valid = g["valid"]
    cluster = orders.join_cluster(body.cluster_code, "") if body.cluster_code else None
    bundle = catalogue.build_bundle(p, extra=body.add, removed=body.remove)
    q = catalogue.quote(p, bundle, cluster_size=cluster["size"] if cluster else 0)
    lines = advisor.llm_rephrase(advisor.explain(p, bundle, q), p.language)
    return {"profile": {**p.__dict__, "needs": sorted(p.needs),
                        "segment_name": catalogue.SEGMENT_KEYS.get(p.segment)},
            "gstin": g, "bundle": bundle, "quote": q, "explanation": lines,
            "grow_ladder": catalogue.grow_ladder_preview(p, bundle), "cluster": cluster}


@app.get("/api/questions")
def questions():
    return advisor.QUESTIONS


@app.get("/api/catalogue")
def get_catalogue():
    df = catalogue.catalogue().reset_index()
    return df.drop(columns=["tiers", "needs_one_of", "segments"]).to_dict(orient="records")


@app.get("/api/gstin/{gstin}")
def gstin_lookup(gstin: str):
    return _gstin_status(gstin)


@app.get("/api/udyam/{number}")
def udyam_lookup(number: str):
    rec = registry.lookup_udyam(number)
    store.audit("udyam.lookup", udyam=registry.mask(registry.normalize_udyam(number)), found=rec is not None)
    if not rec:
        raise HTTPException(404, "Udyam number not found")
    return {**rec, "udyam_number": registry.mask(rec["udyam_number"])}


class ConsentIn(BaseModel):
    purposes: dict[str, bool]
    language: str = "en"


@app.get("/api/consent/purposes")
def consent_purposes():
    return {"purposes": orders.PURPOSES, "retention": orders.RETENTION_TEXT}


@app.post("/api/consent")
def give_consent(body: ConsentIn):
    try:
        return orders.record_consent(body.purposes, body.language)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/consent/{cid}/withdraw")
def withdraw(cid: str):
    try:
        return orders.withdraw_consent(cid)
    except KeyError:
        raise HTTPException(404, "Consent not found")


def _require_consent(cid: str):
    c = store.get("consents", cid)
    if not c or c.get("withdrawn_at") or not c["purposes"].get("kyc"):
        raise HTTPException(403, "KYC consent is required before any document is processed")


@app.post("/api/kyc/verify")
async def kyc_verify(consent_id: str = Form(...), gst_certificate: UploadFile | None = File(None),
                     udyam_certificate: UploadFile | None = File(None), signatory_id: UploadFile | None = File(None),
                     address_proof: UploadFile | None = File(None)):
    _require_consent(consent_id)
    docs = {}
    for name, f in [("gst_certificate", gst_certificate), ("udyam_certificate", udyam_certificate),
                    ("signatory_id", signatory_id), ("address_proof", address_proof)]:
        if f is not None:
            data = await f.read()
            if len(data) > 8 * 1024 * 1024 or (f.content_type or "").split("/")[0] != "image":
                raise HTTPException(400, f"{name}: upload an image under 8 MB")
            docs[name] = data                      # in memory only, never written to disk
    result = kyc.verify(docs)
    store.audit("kyc.verdict", consent_id=consent_id, verdict=result["verdict"])
    return result


@app.post("/api/kyc/specimen/{applicant}")
def kyc_specimen(applicant: str, consent_id: str):
    """Demo: run the pipeline on the dataset's specimen applicants K01-K12."""
    _require_consent(consent_id)
    docs = kyc.load_specimen(applicant.upper())
    if not docs:
        raise HTTPException(404, "Unknown specimen")
    result = kyc.verify(docs)
    store.audit("kyc.verdict", consent_id=consent_id, applicant=applicant.upper(), verdict=result["verdict"])
    return result


class OrderIn(AdviseIn):
    consent_id: str
    saathi_code: str | None = None


@app.post("/api/orders")
def place_order(body: OrderIn):
    _require_consent(body.consent_id)
    res = advise(body)
    if not res["bundle"]["items"]:
        raise HTTPException(400, "Bundle is empty")
    name = body.business_name or (res["gstin"].get("trade_name") if res["gstin"].get("found") else None) or "Your business"
    return orders.create_order(name, res["bundle"]["items"], res["quote"], body.consent_id,
                               body.saathi_code, body.cluster_code)


@app.get("/api/orders/{oid}")
def order_status(oid: str, day: int = 2, delay: int = 0):
    from datetime import timedelta
    from .config import TODAY
    try:
        return orders.track(oid, TODAY + timedelta(days=day), delay_days=delay)
    except KeyError:
        raise HTTPException(404, "Order not found")


class ClusterIn(BaseModel):
    code: str
    business_name: str


@app.post("/api/cluster/join")
def cluster_join(body: ClusterIn):
    return orders.join_cluster(body.code, body.business_name)


@app.get("/api/backoffice/winback")
def backoffice(limit: int = 40):
    return propensity.winback_queue(limit)


@app.get("/api/backoffice/funnel")
def funnel():
    import pandas as pd
    from .config import DATA_DIR
    df = pd.read_csv(DATA_DIR / "smb_leads.csv")
    stages = ["Lead", "Contacted", "Needs assessed", "Quote accepted", "KYC complete", "Activated"]
    reached = df["stage_reached"].map({s: i for i, s in enumerate(stages)})
    act = df[df["outcome"] == "Activated"]
    return {"funnel": [{"stage": s, "count": int((reached >= i).sum())} for i, s in enumerate(stages)],
            "days_to_activate": round(float(act["days_lead_to_activation"].mean()), 1),
            "chase_calls": round(float(act["customer_follow_up_calls"].mean()), 1),
            "cac": round(float(df["acquisition_cost_inr"].sum() / len(act))),
            "commissions": list(store.all_rows("commissions").values())}


@app.get("/api/audit")
def audit_log(limit: int = 50):
    rows = list(store.all_rows("audit").values())
    return rows[-limit:]


@app.get("/")
def root():
    return RedirectResponse("/app/")


@app.get("/backoffice")
def backoffice_page():
    return FileResponse(WEB_DIR / "backoffice.html")


app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="web")
