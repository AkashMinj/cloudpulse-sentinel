"""Transparent utilization-based resource-waste recommendations."""


def build_utilization_recommendations(
    rows, *, cpu_threshold=10.0, memory_threshold=50.0, minimum_samples=10
):
    recommendations = []
    for row in rows:
        instance_id, sample_count, avg_cpu, peak_cpu, avg_memory, peak_memory = row
        avg_cpu = float(avg_cpu or 0)
        peak_cpu = float(peak_cpu or 0)
        avg_memory = float(avg_memory or 0)
        peak_memory = float(peak_memory or 0)
        if sample_count < minimum_samples:
            status = "insufficient_data"
            action = "collect_more_metrics"
            reason = f"Only {sample_count} samples are available; {minimum_samples} are required."
        elif avg_cpu < cpu_threshold and avg_memory < memory_threshold:
            status = "underutilized"
            action = "review_rightsizing_or_schedule"
            reason = f"Average CPU was {avg_cpu:.1f}% and average memory was {avg_memory:.1f}%."
        else:
            status = "utilization_healthy"
            action = "no_change"
            reason = f"Average CPU was {avg_cpu:.1f}% and average memory was {avg_memory:.1f}%."
        recommendations.append({
            "instance_id": instance_id,
            "sample_count": int(sample_count),
            "average_cpu_percent": round(avg_cpu, 2),
            "peak_cpu_percent": round(peak_cpu, 2),
            "average_memory_percent": round(avg_memory, 2),
            "peak_memory_percent": round(peak_memory, 2),
            "status": status,
            "recommended_action": action,
            "reason": reason,
            "estimated_monthly_savings": None,
        })
    return recommendations
