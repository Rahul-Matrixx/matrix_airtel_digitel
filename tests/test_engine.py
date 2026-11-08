"""Run: pytest -q"""
import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from app import advisor, catalogue  # noqa: E402
from app.config import DATA_DIR  # noqa: E402
from app.registry import gstin_check_char, mask, normalize_udyam, repair_gstin, validate_gstin  # noqa: E402


def test_checksum_matches_every_registry_gstin():
    g = pd.read_csv(DATA_DIR / "mock_gstin_registry.csv", dtype=str)["gstin"]
    assert all(gstin_check_char(x[:14]) == x[14] for x in g)


def test_tampered_check_digit_is_caught():
    assert not validate_gstin("37IHKXV5167L1ZT")["checksum_ok"]


def test_ocr_lookalikes_are_repaired_only_when_unique_and_registered():
    assert repair_gstin("27QHIXK0658U1ZL")["gstin"] == "27QHJXK0658U1ZL"
    assert repair_gstin("37THKXV5167L1ZS", "Neha Kaur (Prop. Vindhya Tours & Travels)")["gstin"] == "37IHKXV5167L1ZS"


def test_udyam_normalisation_and_masking():
    assert normalize_udyam("UDYAM-MH- 00-6131836") == "UDYAM-MH-00-6131836"
    assert mask("37IHKXV5167L1ZS") == "37••••••••••1ZS"


def test_hinglish_sentence_is_understood():
    f = advisor.parse_free_text("kirana hai, 3 log, UPI aur CCTV chahiye, Jaipur")
    assert f["segment"] == "micro" and f["employees"] == 3 and {"upi", "cctv"} <= f["needs"]
    assert f["city"] == "Jaipur" and f["language"] == "hi"


def test_no_gstin_shop_never_gets_gst_gated_products():
    p = advisor.profile_from({"text": "kirana, 3 log, whatsapp aur cctv chahiye, Jaipur"})
    b = catalogue.build_bundle(p)
    cat = catalogue.catalogue()
    assert all(cat.loc[i["product_id"]].requires_gstin == "N" for i in b["items"])
    assert any(w["product_id"] == "P15" and "GSTIN" in w["reason"] for w in b["withheld"])
    assert catalogue.grow_ladder_preview(p, b)["unlocks"] == ["WhatsApp Business API Starter"]


@pytest.mark.parametrize("text", [
    "kirana hai, 3 log, UPI aur CCTV chahiye, Jaipur",
    "dental clinic in Pune, 8 staff, email backup wifi",
    "restaurant chain with 5 outlets in Mumbai, 40 staff, POS, CCTV",
    "auto parts factory, 30 workers, Pune, sensors and firewall",
])
def test_every_bundle_satisfies_every_catalogue_rule(text):
    for gst in (False, True):
        p = advisor.profile_from({"text": text})
        p.gstin_valid = gst
        b = catalogue.build_bundle(p)
        ids = {i["product_id"] for i in b["items"]}
        for pid in ids:
            assert catalogue.check_item(pid, p, ids) is None, (text, gst, pid)


def test_removing_the_line_also_removes_what_depends_on_it():
    p = advisor.profile_from({"text": "kirana, 2 log, cctv chahiye, Jaipur"})
    b = catalogue.build_bundle(p, removed=["P04", "P01"])
    assert "P23" not in {i["product_id"] for i in b["items"]}


def test_quote_is_deterministic_and_has_rozana_and_bill_swap():
    p = advisor.profile_from({"text": "dental clinic in Pune, 8 staff, email backup wifi"})
    q1 = catalogue.quote(p, catalogue.build_bundle(p))
    q2 = catalogue.quote(p, catalogue.build_bundle(p))
    assert q1 == q2
    assert q1["rozana_per_day"] == round(q1["monthly_net"] / 30)
    assert q1["bill_swap"]["saving_per_month"] > 0


def test_switch_shield_is_capped():
    p = advisor.profile_from({"text": "kirana, Jaipur"})
    p.locked_in, p.current_spend = True, 9000
    assert catalogue.quote(p, catalogue.build_bundle(p))["switch_shield_credit"] == 5000
