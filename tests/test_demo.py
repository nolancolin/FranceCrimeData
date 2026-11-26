from delinquance.demo import rates_by_indicator, round_coords


def test_round_coords_keeps_nesting():
    assert round_coords([[[2.123456, 48.98765], [3.0, 49.0]]]) == [[[2.123, 48.988], [3.0, 49.0]]]


def test_rates_by_indicator_covers_every_row(cleaned):
    rates = rates_by_indicator(cleaned)
    assert sum(len(deps) for years in rates.values() for deps in years.values()) == len(cleaned)
    assert rates["Homicides"]["2025"]["75"] > 0
