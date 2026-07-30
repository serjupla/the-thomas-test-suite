from thomas.report.strings import STRINGS


def test_en_and_pt_define_the_exact_same_key_set():
    assert set(STRINGS["en"].keys()) == set(STRINGS["pt"].keys())
