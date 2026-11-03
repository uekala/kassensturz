import pytest

from kassensturz import importers
from kassensturz.util import parse_amount, parse_date, split_sepa_purpose

from conftest import fixture_bytes


@pytest.mark.parametrize("raw,cents", [
    ("1.234,56", 123456), ("-12,30 €", -1230), ("1,234.56", 123456), ("12.5", 1250), ("-4.8", -480),
    ("(3,00)", -300), ("12,00-", -1200), ("3.450,12", 345012), ("−15,99", -1599), ("0,00", 0), ("", None), ("abc", None),
])
def test_parse_amount(raw, cents):
    assert parse_amount(raw) == cents


def test_parse_date_variants():
    assert parse_date("30.10.26").isoformat() == "2026-10-30"
    assert parse_date("30.10.2026").isoformat() == "2026-10-30"
    assert parse_date("2026-10-31 09:00:00").isoformat() == "2026-10-31"
    assert parse_date("30/10/2026").isoformat() == "2026-10-30"
    assert parse_date("offen") is None


def test_sepa_purpose():
    f = split_sepa_purpose("EREF+NF-123 MREF+NFX-9 CRED+NL55ZZZ000000000001 SVWZ+Netflix Abo")
    assert f["SVWZ"] == "Netflix Abo" and f["MREF"] == "NFX-9" and f["CRED"] == "NL55ZZZ000000000001"


EXPECTED = {
    "sparkasse.csv": ("Sparkasse", 4, {"-8900": "Stadtwerke Musterstadt AG"}),
    "volksbank.csv": ("Volksbank / Raiffeisenbank", 3, {"-4495": "Telekom Deutschland GmbH"}),
    "ing.csv": ("ING", 3, {"-105000": "Wohnbau Niederrhein eG"}),
    "dkb.csv": ("DKB", 2, {"-41238": "HUK-COBURG", "345012": "Muster Systemhaus GmbH"}),
    "comdirect.csv": ("comdirect", 2, {"-2995": "Telekom Deutschland GmbH"}),
    "n26.csv": ("N26", 3, {"-1245": "dm-drogerie markt"}),
    "revolut.csv": ("Revolut", 3, {"-10200": "Cash at ATM"}),
    "paypal.csv": ("PayPal", 4, {"-5995": "Zalando SE"}),
    "amex.csv": ("American Express", 3, {"-1599": "NETFLIX.COM", "41200": "ZAHLUNG ERHALTEN. BESTEN DANK"}),
    "advanzia_export.csv": ("Advanzia", 2, {"-12990": "IKEA Kaarst"}),
    "camt.xml": ("CAMT", 2, {"-8900": "Stadtwerke Musterstadt AG"}),
    "konto.sta": ("MT940", 2, {"345012": "Muster Systemhaus GmbH", "-1599": "Netflix International B.V."}),
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_formats(name):
    label, count, samples = EXPECTED[name]
    res = importers.analyze(fixture_bytes(name), name)
    assert res["format"] == label
    assert res["count"] == count, res.get("skipped")
    by_amount = {str(r["amount_cents"]): r["counterparty"] for r in res["rows"]}
    for amount, cp in samples.items():
        assert by_amount.get(amount) == cp


def test_balance_and_iban_detection():
    ing = importers.analyze(fixture_bytes("ing.csv"), "ing.csv")
    assert ing["meta"]["iban"] == "DE89500105171234567890"
    assert ing["meta"]["balance_cents"] == 123456
    dkb = importers.analyze(fixture_bytes("dkb.csv"), "dkb.csv")
    assert dkb["meta"]["balance_cents"] == 234567 and dkb["meta"]["balance_date"] == "2026-11-02"
    vb = importers.analyze(fixture_bytes("volksbank.csv"), "volksbank.csv")
    assert vb["meta"]["balance_cents"] == 195505
    camt = importers.analyze(fixture_bytes("camt.xml"), "camt.xml")
    assert camt["meta"] == {"iban": "DE12320500000012345678", "balance_cents": 250000, "balance_date": "2026-10-31"}


def test_sepa_fields_survive():
    sta = importers.analyze(fixture_bytes("konto.sta"), "konto.sta")
    nf = next(r for r in sta["rows"] if r["amount_cents"] == -1599)
    assert nf["creditor_id"] == "NL55ZZZ000000000001" and nf["mandate_ref"] == "NFX-9" and nf["purpose"] == "Netflix Abo"
    salary = next(r for r in sta["rows"] if r["amount_cents"] > 0)
    assert salary["counterparty_iban"] == "DE44500105175407324931"


def test_mapping_override_inverts():
    res = importers.analyze(fixture_bytes("advanzia_export.csv"), "export.csv", {"invert": True})
    assert sorted(r["amount_cents"] for r in res["rows"]) == [-30000, 12990]


def test_unknown_file_gives_hint():
    res = importers.analyze(b"hallo;welt\n1;2\n", "x.csv")
    assert res.get("error")
