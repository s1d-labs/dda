"""NIT keys: the DDA site and eprocure write one tender reference in different ways."""
from link_eprocure import nit_key


def test_same_tender_same_key():
    assert nit_key("07/EE/ELD-8/DDA/2026-27") == nit_key("NIT No. 7/EE/ELD-8/DDA/NIT/2026-27") == "7|EEELD8|2026-27"
    assert nit_key("07/EE/ELD-1/DDA/NIT/2025-26_R6") == "7|EEELD1|2025-26"          # re-tender round
    assert nit_key("03/SSC/DDA/2026-27/Re-invited") == "3|SSC|2026-27"
    assert nit_key("E-Tender Notice No: 05/21-22/HD-III/DDA") == "5|HDIII|2021-22"


def test_quotation_series_is_separate():
    assert nit_key("NIQ NO. 03/HNSC/DDA/2022-23") == "Q3|HNSC|2022-23"
    assert nit_key("NIQ NO. 03/HNSC/DDA/2022-23") != nit_key("NIT No. 03/HNSC/DDA/2022-23")


def test_no_key_without_year_or_office():
    assert nit_key("NIT No. 144/19-20/ Hort. Dwk.") == "144|HORTDWK|2019-20"
    assert nit_key("Tender for kiosks") is None
    assert nit_key(None) is None
