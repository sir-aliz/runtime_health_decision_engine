from fastapi import APIRouter, HTTPException
import sqlite3

from .aggregation import aggregate_metrics
from .analysis import analyze
from .classification import classify_health
from .decision import make_decision
from .logger import logger
from .models import DeploymentData, MetricData
from . import storage

router = APIRouter()


@router.post('/metrics')
def ingest_metrics(metric_data: MetricData):
    try:
        storage.add_metric(metric_data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    aggregated = aggregate_metrics(metric_data.model_dump())
    if metric_data.request_count == 0:
        return {'health_state': 'Unknown', 'action': 'Collect more data',
                'reason': 'No requests were observed in this bucket'}
    decision = make_decision(classify_health(aggregated), aggregated)
    logger.info('Processed metrics', extra={'decision': decision.model_dump(),
                                           'service_id': metric_data.service_id})
    return decision


@router.post('/deployments', status_code=201)
def create_deployment(deployment: DeploymentData):
    try:
        return storage.add_deployment(deployment)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail='This deployment is already recorded') from exc


@router.get('/deployments')
def deployments():
    return storage.list_deployments()


@router.get('/deployments/{deployment_id}/analysis')
def deployment_analysis(deployment_id: str):
    deployment = storage.get_deployment(deployment_id)
    if not deployment:
        raise HTTPException(status_code=404, detail='Deployment not found')
    return analyze(deployment)
