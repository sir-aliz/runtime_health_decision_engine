def aggregate_metrics(raw_data: dict) -> dict:
    """
    Computes derived metrics from raw input.
    For MVP, we calculate error_rate from error_count and request_count.
    """
    req_count = raw_data.get("request_count", 0)
    err_count = raw_data.get("error_count", 0)
    
    error_rate = 0.0
    if req_count > 0:
        error_rate = err_count / req_count
        
    return {
        "service_id": raw_data.get("service_id"),
        "latency_ms": raw_data.get("latency_ms"),
        "error_rate": error_rate,
        "request_count": req_count
    }
