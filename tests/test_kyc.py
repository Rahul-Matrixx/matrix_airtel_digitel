"""Smart KYC against the 12 specimen applicants (needs Tesseract installed). Run: pytest -q"""
import sys
import warnings
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from app.kyc import load_specimen, verify  # noqa: E402

EXPECTED = {
    "K01": ("REJECTED", ["Cancelled", "blank"]),
    "K04": ("NEEDS_REVIEW", ["blurred"]),
    "K05": ("NEEDS_REVIEW", ["Missing udyam"]),
    "K07": ("REJECTED", ["legal name"]),
    "K10": ("NEEDS_REVIEW", ["designated partner"]),
    "K11": ("REJECTED", ["257 days"]),
    "K03": ("APPROVED", []),
}


@pytest.mark.parametrize("applicant,expected", EXPECTED.items())
def test_specimen_verdicts(applicant, expected):
    verdict, phrases = expected
    r = verify(load_specimen(applicant))
    assert r["verdict"] == verdict
    joined = " ".join(r["reasons"])
    for ph in phrases:
        assert ph.lower() in joined.lower(), (applicant, ph, joined)


def test_identifiers_are_masked_in_output():
    r = verify(load_specimen("K03"))
    assert "•" in r["fields"]["gst_certificate"]["gstin"]
