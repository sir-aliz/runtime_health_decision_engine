from .config import THRESHOLDS

def classify_health(metrics: dict) -> str:
    """
    Classifies service health based on metrics and configured thresholds.
    Returns: "Healthy", "Degraded", or "Critical"
    """
    thresholds = THRESHOLDS.get("default")
    
    latency = metrics.get("latency_ms", 0)
    error_rate = metrics.get("error_rate", 0.0)
    
    # Critical checks
    if latency > thresholds["latency_critical_ms"] or error_rate > thresholds["error_rate_critical"]:
        return "Critical"
        
    # Degraded checks
    if latency > thresholds["latency_degraded_ms"] or error_rate > thresholds["error_rate_degraded"]:
        return "Degraded"
        
    return "Healthy"
