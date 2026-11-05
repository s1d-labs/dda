"""Colony registration numbers: one key for the list PDF and the boundary table."""
from extract_colonies import pin_of, reg_key


def test_reg_key_forms():
    assert reg_key("REGD. No.732 B") == "732B"
    assert reg_key("8", "A") == "8A"
    assert reg_key("90-(ELD)") == reg_key("90ELD") == "90-ELD"
    assert reg_key("08LOP") == reg_key("8-(LOP)") == "8-LOP"
    assert reg_key("1476_B") == "1476B"
    assert reg_key("REGD. No.20.") == "20"
    assert reg_key("") is None


def test_pin():
    assert pin_of("Inder Prasth Colony, Burari, Delhi-84") == "110084"
    assert pin_of("Raza Pur Village, Rohini Delhi 85") == "110085"
    assert pin_of("Ladakh Budh Vihar Colony") is None
