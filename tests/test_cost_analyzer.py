from app.cost_analyzer import build_utilization_recommendations


def test_underutilized_resource_is_flagged():
    item = build_utilization_recommendations([
        ("i-0123456789abcdef0", 20, 4.5, 12.0, 31.0, 44.0)
    ])[0]
    assert item["status"] == "underutilized"
    assert item["recommended_action"] == "review_rightsizing_or_schedule"
    assert item["estimated_monthly_savings"] is None


def test_insufficient_history_is_not_overstated():
    item = build_utilization_recommendations([
        ("i-0123456789abcdef0", 3, 1.0, 2.0, 20.0, 25.0)
    ])[0]
    assert item["status"] == "insufficient_data"


def test_healthy_resource_has_no_change_recommendation():
    item = build_utilization_recommendations([
        ("i-0123456789abcdef0", 20, 45.0, 90.0, 60.0, 90.0)
    ])[0]
    assert item["status"] == "utilization_healthy"
