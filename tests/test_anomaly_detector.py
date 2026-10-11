import pytest

from app.anomaly_detector import ResourceAnomalyDetector


def make_metric(cpu, memory, disk):
    return {
        "cpu_usage_percent": cpu,
        "memory_usage_percent": memory,
        "disk_usage_percent": disk,
    }


def test_detector_can_train_and_predict():
    training_data = [
        make_metric(10, 40, 30),
        make_metric(12, 42, 31),
        make_metric(8, 39, 29),
        make_metric(15, 43, 32),
        make_metric(11, 41, 30),
        make_metric(9, 40, 31),
        make_metric(13, 42, 30),
        make_metric(10, 41, 29),
        make_metric(14, 43, 31),
        make_metric(12, 40, 30),
        make_metric(9, 42, 32),
        make_metric(11, 39, 30),
    ]

    detector = ResourceAnomalyDetector(contamination=0.05)
    detector.fit(training_data)

    result = detector.predict(make_metric(10, 41, 30))

    assert isinstance(result.is_anomaly, bool)
    assert isinstance(result.anomaly_score, float)


def test_extreme_resource_usage_is_detected():
    training_data = [
        make_metric(10, 40, 30),
        make_metric(12, 42, 31),
        make_metric(8, 39, 29),
        make_metric(15, 43, 32),
        make_metric(11, 41, 30),
        make_metric(9, 40, 31),
        make_metric(13, 42, 30),
        make_metric(10, 41, 29),
        make_metric(14, 43, 31),
        make_metric(12, 40, 30),
        make_metric(9, 42, 32),
        make_metric(11, 39, 30),
    ]

    detector = ResourceAnomalyDetector(contamination=0.05)
    detector.fit(training_data)

    result = detector.predict(make_metric(100, 99, 95))

    assert result.is_anomaly is True


def test_training_requires_at_least_ten_samples():
    detector = ResourceAnomalyDetector()

    with pytest.raises(ValueError):
        detector.fit(
            [
                make_metric(10, 40, 30),
                make_metric(12, 42, 31),
            ]
        )


def test_prediction_requires_training():
    detector = ResourceAnomalyDetector()

    with pytest.raises(RuntimeError):
        detector.predict(make_metric(10, 40, 30))


def test_missing_feature_is_rejected():
    detector = ResourceAnomalyDetector()

    with pytest.raises(ValueError):
        detector.fit(
            [
                {
                    "cpu_usage_percent": 10,
                    "memory_usage_percent": 40,
                }
            ]
            * 10
        )

def test_detector_separates_held_out_normal_and_extreme_metrics():
    training_data = [
        make_metric(10, 40, 30),
        make_metric(12, 42, 31),
        make_metric(8, 39, 29),
        make_metric(15, 43, 32),
        make_metric(11, 41, 30),
        make_metric(9, 40, 31),
        make_metric(13, 42, 30),
        make_metric(10, 41, 29),
        make_metric(14, 43, 31),
        make_metric(12, 40, 30),
        make_metric(9, 42, 32),
        make_metric(11, 39, 30),
        make_metric(13, 41, 31),
        make_metric(10, 42, 30),
        make_metric(12, 40, 32),
        make_metric(8, 41, 29),
        make_metric(14, 42, 30),
        make_metric(11, 40, 31),
        make_metric(9, 43, 30),
        make_metric(12, 41, 29),
    ]

    detector = ResourceAnomalyDetector(contamination=0.05)
    detector.fit(training_data)

    normal_samples = [
        make_metric(10, 41, 30),
        make_metric(12, 42, 31),
        make_metric(9, 40, 30),
    ]
    extreme_samples = [
        make_metric(99, 99, 99),
        make_metric(100, 95, 98),
        make_metric(98, 99, 95),
    ]

    normal_predictions = [
        detector.predict(sample).is_anomaly for sample in normal_samples
    ]
    extreme_predictions = [
        detector.predict(sample).is_anomaly for sample in extreme_samples
    ]

    assert normal_predictions == [False, False, False]
    assert extreme_predictions == [True, True, True]
