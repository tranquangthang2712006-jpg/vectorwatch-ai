"""Test đơn vị cho scoring service: giá trị biên, thiếu dữ liệu, tính lặp lại."""
import pytest

from app.services import scoring


def feats(rain=40, temp=27.5, hum=72, water=5, survey=1 / 3):
    return {"rainfall_7d": rain, "temperature_mean": temp, "humidity_mean": hum, "water_points_active": water,
            "survey_positive_ratio": survey, "_meta": {}}


def test_weights_sum_to_one():
    assert sum(scoring.SPECIES_REGISTRY["aedes"]["ess_weights"].values()) == pytest.approx(1.0)
    assert sum(scoring.PIS_WEIGHTS.values()) == pytest.approx(1.0)


def test_ess_matches_hand_calculation_and_is_repeatable():
    a, b = scoring.compute_ess(feats()), scoring.compute_ess(feats())
    assert a["ess"] == pytest.approx(53.9, abs=0.1)
    assert a["ess_class"]["key"] == "medium"
    assert a == b


@pytest.mark.parametrize("value,expected", [(0, 0), (100, 100), (150, 100), (300, 60), (1000, 60), (50, 50)])
def test_rainfall_curve_boundaries(value, expected):
    curve = scoring.SPECIES_REGISTRY["aedes"]["curves"]["rainfall"]
    assert scoring.interpolate(curve, value) == pytest.approx(expected)


def test_heavy_rain_does_not_keep_increasing_score():
    moderate = scoring.compute_ess(feats(rain=120))["ess"]
    extreme = scoring.compute_ess(feats(rain=300))["ess"]
    assert extreme < moderate


@pytest.mark.parametrize("score,key", [(0, "very_low"), (24.9, "very_low"), (25, "low"), (49.9, "low"), (50, "medium"),
                                       (74.9, "medium"), (75, "high"), (89.9, "high"), (90, "very_high"), (100, "very_high")])
def test_ess_class_thresholds(score, key):
    assert scoring.classify_ess(score)["key"] == key


def test_missing_value_is_not_treated_as_zero():
    full = scoring.compute_ess(feats(hum=0))       # độ ẩm thật sự bằng 0
    missing = scoring.compute_ess(feats(hum=None))  # độ ẩm thiếu
    hum = next(c for c in missing["components"] if c["key"] == "humidity")
    assert hum["score"] is None and hum["missing"]
    assert missing["status"] == "partial" and missing["completeness"] == pytest.approx(0.85)
    assert missing["ess"] > full["ess"]
    assert sum(c["effective_weight"] for c in missing["components"]) == pytest.approx(1.0, abs=0.001)


def test_insufficient_data_returns_no_score():
    result = scoring.compute_ess(feats(temp=None, hum=None, water=None))
    assert result["status"] == "insufficient_data" and result["ess"] is None
    assert scoring.compute_pis(None, 50, 50, 0)["pis"] is None


def test_unconfigured_species_is_rejected():
    assert scoring.compute_ess(feats(), "culex")["status"] == "unsupported_species"


def test_pis_formula_and_renormalisation():
    full = scoring.compute_pis(80, 60, 40, 20)
    assert full["pis"] == pytest.approx(0.35 * 80 + 0.25 * 60 + 0.25 * 40 + 0.15 * 20, abs=0.1)
    partial = scoring.compute_pis(80, 60, None, None)
    assert partial["pis"] == pytest.approx((0.35 * 80 + 0.25 * 60) / 0.60, abs=0.1)
    assert set(partial["missing"]) == {"survey", "change"}


def test_change_score_only_counts_increase():
    assert scoring.compute_change_score(70, 60) == 50
    assert scoring.compute_change_score(60, 70) == 0
    assert scoring.compute_change_score(95, 20) == 100
    assert scoring.compute_change_score(60, None) is None
