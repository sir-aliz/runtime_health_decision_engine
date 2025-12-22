from pydantic import BaseModel

class DecisionResult(BaseModel):
    health_state: str
    action: str
    reason: str

def make_decision(health_state: str, metrics: dict) -> DecisionResult:
    """
    Determines the recommended action based on health state.
    """
    if health_state == "Critical":
        return DecisionResult(
            health_state=health_state,
            action="Alert & Fallback",
            reason=f"High latency ({metrics.get('latency_ms')}ms) or error rate ({metrics.get('error_rate'):.2f})"
        )
    elif health_state == "Degraded":
        return DecisionResult(
            health_state=health_state,
            action="Monitor & Auto-Retry",
            reason="Metrics exceed warning thresholds"
        )
    else:
        return DecisionResult(
            health_state=health_state,
            action="No Action",
            reason="System operating within normal limits"
        )
