from backend.services.statistics import mean_delta, minimum_detectable_effect_warning, wilson_interval


def test_wilson_interval_and_delta_helpers_are_stable():
    interval = wilson_interval(80, 100)

    assert 0.7 < interval["low"] < 0.8
    assert 0.8 < interval["high"] < 0.9
    assert mean_delta(0.85, 0.8) == 0.05
    assert minimum_detectable_effect_warning(25, 50) == "Underpowered: 25 samples is below configured minimum 50."
    assert minimum_detectable_effect_warning(50, 50) is None
