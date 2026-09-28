from app.domain.identifiers import is_valid_dic, is_valid_iban, is_valid_ic_dph, is_valid_ico


def test_ico_checksum():
    assert is_valid_ico("36070963")
    assert is_valid_ico("35757442")
    assert not is_valid_ico("36070964")
    assert not is_valid_ico("1234")


def test_dic():
    assert is_valid_dic("2020123457")
    assert not is_valid_dic("020123457")
    assert not is_valid_dic("20201234")


def test_ic_dph():
    assert is_valid_ic_dph("SK2020123457")
    assert is_valid_ic_dph("sk 2020261342")
    assert not is_valid_ic_dph("SK2020123456")  # not divisible by 11
    assert not is_valid_ic_dph("SK2010123450")  # third digit must be 2,3,4,7,8,9
    assert not is_valid_ic_dph("CZ12345678")


def test_iban():
    assert is_valid_iban("SK31 1200 0000 1987 4263 7541")
    assert not is_valid_iban("SK31 1200 0000 1987 4263 7542")
    assert not is_valid_iban("SK3112000000")
