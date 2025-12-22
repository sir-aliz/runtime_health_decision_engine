from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

from .aggregation import aggregate_metrics
from .classification import classify_health
from .decision import make_decision
from .logger import logger

router = APIRouter()

class MetricData(BaseModel):
    service_id: str
    timestamp: str
    latency_ms: float
    error_count: int
    request_count: int

@router.post("/metrics")
async def ingest_metrics(metric_data: MetricData):
    """
    Ingests raw metrics, processes them, and returns a health decision.
    """
    try:
        # Step 1: Aggregation
        aggregated = aggregate_metrics(metric_data.dict())
        
        # Step 2: Classification
        health_state = classify_health(aggregated)
        
        # Step 3: Decision
        decision = make_decision(health_state, aggregated)
        
        # Step 4: Logging
        logger.info(
            f"Processed metrics for {metric_data.service_id}", 
            extra={
                "decision": decision.dict(),
                "service_id": metric_data.service_id
            }
        )
        
        return decision
        
    except Exception as e:
        logger.error(f"Error processing metrics: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
