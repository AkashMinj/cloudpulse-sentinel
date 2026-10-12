import numpy as np
from sklearn.metrics import (
    confusion_matrix,
    classification_report,
    precision_score,
    recall_score,
    f1_score,
)

from app.anomaly_detector import ResourceAnomalyDetector, FEATURES


def make_metrics(values):
    return [
        dict(zip(FEATURES, row))
        for row in values
    ]


def main():
    rng = np.random.default_rng(42)

    # Synthetic normal workload: moderate resource utilization.
    train_values = np.column_stack([
        rng.normal(25, 8, 1000),
        rng.normal(50, 7, 1000),
        rng.normal(45, 8, 1000),
    ])
    train_values = np.clip(train_values, 0, 100)

    # Held-out normal samples.
    normal_values = np.column_stack([
        rng.normal(25, 8, 200),
        rng.normal(50, 7, 200),
        rng.normal(45, 8, 200),
    ])
    normal_values = np.clip(normal_values, 0, 100)

    # Synthetic anomalies: extreme resource utilization.
    anomaly_values = np.column_stack([
        rng.uniform(90, 100, 50),
        rng.uniform(90, 100, 50),
        rng.uniform(90, 100, 50),
    ])

    detector = ResourceAnomalyDetector(
        contamination=0.05,
        random_state=42,
    )
    detector.fit(make_metrics(train_values))

    test_values = np.vstack([normal_values, anomaly_values])
    y_true = np.array([0] * len(normal_values) + [1] * len(anomaly_values))

    results = [
        detector.predict(dict(zip(FEATURES, row)))
        for row in test_values
    ]
    y_pred = np.array([int(result.is_anomaly) for result in results])

    tn, fp, fn, tp = confusion_matrix(
        y_true, y_pred, labels=[0, 1]
    ).ravel()

    print("OFFLINE SYNTHETIC EVALUATION")
    print(f"Training samples: {len(train_values)}")
    print(f"Test samples: {len(test_values)}")
    print(f"True positives: {tp}")
    print(f"False positives: {fp}")
    print(f"True negatives: {tn}")
    print(f"False negatives: {fn}")
    print(f"Precision: {precision_score(y_true, y_pred, zero_division=0):.3f}")
    print(f"Recall: {recall_score(y_true, y_pred, zero_division=0):.3f}")
    print(f"F1 score: {f1_score(y_true, y_pred, zero_division=0):.3f}")
    print(f"False-positive rate: {fp / (fp + tn):.3f}")

    print("\nClassification report:")
    print(classification_report(
        y_true,
        y_pred,
        target_names=["normal", "anomaly"],
        zero_division=0,
    ))
    evaluate_realistic_scenarios(detector, rng)

def evaluate_realistic_scenarios(detector, rng):
    scenarios = {
        "High CPU only": [
            {"cpu_usage_percent": 98, "memory_usage_percent": 50, "disk_usage_percent": 45}
        ],
        "High memory only": [
            {"cpu_usage_percent": 25, "memory_usage_percent": 98, "disk_usage_percent": 45}
        ],
        "High disk only": [
            {"cpu_usage_percent": 25, "memory_usage_percent": 50, "disk_usage_percent": 98}
        ],
        "Gradual resource increase": [
            {"cpu_usage_percent": 65, "memory_usage_percent": 70, "disk_usage_percent": 65},
            {"cpu_usage_percent": 75, "memory_usage_percent": 75, "disk_usage_percent": 70},
            {"cpu_usage_percent": 85, "memory_usage_percent": 80, "disk_usage_percent": 75},
        ],
        "Borderline readings": [
            {"cpu_usage_percent": 80, "memory_usage_percent": 65, "disk_usage_percent": 50},
            {"cpu_usage_percent": 50, "memory_usage_percent": 80, "disk_usage_percent": 65},
            {"cpu_usage_percent": 50, "memory_usage_percent": 65, "disk_usage_percent": 80},
        ],
    }

    print("\nREALISTIC SCENARIO EVALUATION")
    for name, samples in scenarios.items():
        print(f"\n{name}:")
        for sample in samples:
            result = detector.predict(sample)
            print(
                f"  CPU={sample['cpu_usage_percent']:>5.1f}% "
                f"MEM={sample['memory_usage_percent']:>5.1f}% "
                f"DISK={sample['disk_usage_percent']:>5.1f}% "
                f"=> {'ANOMALY' if result.is_anomaly else 'NORMAL'} "
                f"(score={result.anomaly_score:.4f})"
            )
if __name__ == "__main__":
    main()
