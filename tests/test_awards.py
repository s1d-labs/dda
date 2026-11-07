"""Award letter values from noisy text: labels, nearest amounts, no guarantee/FDR amounts, no account numbers."""
from analysis.extract_awards import parse_letter


def test_estimate_and_tendered_amount():
    t = ("Your item rate tender has been accepted on behalf of DDA as under :1. Estimated Cost: Rs.19,76,950/- "
         "(Rs Nineteen lakh) 2. Quoted Amount: Rs. 17,12,300/- 3. PG submitted vide FDR no. KO998976 dt. 31.03.2020 "
         "for Rs 88,200.00 Dated: 12.04.2020")
    assert parse_letter(t)[:3] == ("2020-04-12", 1976950.0, 1712300.0)


def test_percent_below_estimate():
    t = "Estimated Cost : Rs. 10,00,000 /- ... 43.10 % (Forty Three Point Ten) below the estimated cost"
    _, est, tnd, _ = parse_letter(t)
    assert est == 1000000 and tnd == 569000.0


def test_guarantee_and_account_numbers_are_not_values():
    t = "Performance guarantee FDR A/c No 50301380677890 for Rs. 52,776/-. Estimated cost 4,00,000"
    _, est, tnd, _ = parse_letter(t)
    assert est == 400000 and tnd is None


def test_tender_id_in_letter():
    assert parse_letter("Tender ID 2025 DDA 876326_1 NIT")[3] == "2025_DDA_876326_1"
