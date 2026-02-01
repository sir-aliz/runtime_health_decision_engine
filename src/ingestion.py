from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator
from typing import Dict, Any, List, Optional, Literal
import os
import json
import re
from pathlib import Path
from enum import Enum
import asyncio
import aiofiles

from .aggregation import aggregate_metrics
from .classification import classify_health
from .decision import make_decision
from .logger import logger
from .config import SECURITY, PERFORMANCE, LOG_PARSING

router = APIRouter()

class MetricData(BaseModel):
    service_id: str
    timestamp: str
    latency_ms: float
    error_count: int
    request_count: int

class IngestionMode(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    SELECTION = "selection"

class LineRange(BaseModel):
    start: int = Field(ge=0, description="Starting line number (0-based)")
    end: int = Field(gt=0, description="Ending line number (exclusive)")

    @validator('end')
    def end_must_be_greater_than_start(cls, v, values):
        if 'start' in values and v <= values['start']:
            raise ValueError('end must be greater than start')
        return v

class LogIngestionRequest(BaseModel):
    directory_path: str = Field(..., min_length=1, max_length=255, description="Directory path for log files")
    file_pattern: Optional[str] = Field("*.log", max_length=100, description="File pattern to match (e.g., *.log, app-*.txt)")
    ingestion_mode: IngestionMode = IngestionMode.FULL
    line_range: Optional[LineRange] = None

    @validator('directory_path')
    def validate_directory_path(cls, v):
        # Basic sanitization
        if any(pattern in v for pattern in ['../', '..\\', '~/', '$HOME']):
            raise ValueError('Directory path contains unsafe characters')
        return v.strip()

    @validator('file_pattern')
    def validate_file_pattern(cls, v):
        if v:
            # Prevent dangerous patterns
            if any(char in v for char in ['|', '&', ';', '$', '`', '"', "'"]):
                raise ValueError('File pattern contains unsafe characters')
        return v

class FileInfo(BaseModel):
    path: str
    size: int
    modified_time: str
    line_count: Optional[int] = None

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

def validate_path_safety(file_path: str, base_paths: Optional[List[str]] = None) -> bool:
    """
    Validate that a path is safe and doesn't contain directory traversal.
    """
    if base_paths is None:
        base_paths = SECURITY["allowed_base_paths"]
    
    # Normalize the path
    normalized_path = os.path.normpath(file_path)
    resolved_path = os.path.abspath(normalized_path)
    
    # Check for blocked patterns
    for blocked in SECURITY["blocked_patterns"]:
        if blocked in file_path:
            logger.warning(f"Blocked pattern '{blocked}' found in path: {file_path}")
            return False
    
    # Check if path is under any allowed base path
    for base_path in base_paths or SECURITY["allowed_base_paths"]:
        abs_base = os.path.abspath(base_path)
        if resolved_path.startswith(abs_base + os.sep) or resolved_path == abs_base:
            # Check path depth
            relative_path = os.path.relpath(resolved_path, abs_base)
            depth = len(relative_path.split(os.sep))
            if depth <= SECURITY["max_path_depth"]:
                return True
    
    logger.warning(f"Path {file_path} is not under allowed base paths: {base_paths}")
    return False

def validate_file_size(file_path: Path) -> bool:
    """
    Validate file size against configured limits.
    """
    try:
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        if file_size_mb > LOG_PARSING["max_file_size_mb"]:
            logger.warning(f"File {file_path} exceeds size limit: {file_size_mb:.2f}MB > {LOG_PARSING['max_file_size_mb']}MB")
            return False
        return True
    except Exception as e:
        logger.error(f"Error checking file size for {file_path}: {str(e)}")
        return False

def validate_line_range(line_range: Optional[Dict[str, int]], max_lines: int) -> Optional[Dict[str, int]]:
    """
    Validate and normalize line range.
    """
    if not line_range:
        return None
    
    start = max(0, line_range.get("start", 0))
    end = min(max_lines, line_range.get("end", max_lines))
    
    if start >= end:
        raise HTTPException(status_code=400, detail="Invalid line range: start must be less than end")
    
    if (end - start) > LOG_PARSING["max_lines_per_batch"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Line range too large: {end - start} > {LOG_PARSING['max_lines_per_batch']}"
        )
    
    return {"start": start, "end": end}

def discover_log_files(directory_path: str, file_pattern: str = "*.log") -> List[FileInfo]:
    """
    Discover log files in the specified directory with security validation.
    """
    try:
        # Validate directory path safety
        if not validate_path_safety(directory_path):
            raise HTTPException(status_code=403, detail="Access denied: path not allowed")
        
        directory = Path(directory_path)
        if not directory.exists():
            raise HTTPException(status_code=404, detail="Directory not found")
        
        if not directory.is_dir():
            raise HTTPException(status_code=400, detail="Path is not a directory")
        
        files = []
        for file_path in directory.glob(file_pattern):
            if file_path.is_file():
                # Validate file path safety
                if not validate_path_safety(str(file_path)):
                    logger.warning(f"Skipping file with unsafe path: {file_path}")
                    continue
                
                # Validate file size
                if not validate_file_size(file_path):
                    logger.warning(f"Skipping file exceeding size limit: {file_path}")
                    continue
                
                stat = file_path.stat()
                line_count = None
                try:
                    # Count lines efficiently for smaller files only
                    if stat.st_size < 10 * 1024 * 1024:  # 10MB
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            line_count = sum(1 for _ in f)
                    else:
                        # For large files, estimate line count
                        line_count = -1  # Indicates "too large to count"
                except Exception as e:
                    logger.debug(f"Could not count lines for {file_path}: {str(e)}")
                
                files.append(FileInfo(
                    path=str(file_path),
                    size=stat.st_size,
                    modified_time=str(stat.st_mtime),
                    line_count=line_count
                ))
        
        return sorted(files, key=lambda x: x.modified_time, reverse=True)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error discovering log files: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error discovering files: {str(e)}")

def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parse a single log line and extract metrics.
    Supports JSON logs and common structured formats.
    """
    line = line.strip()
    if not line:
        return None
    
    # Try JSON format first
    try:
        log_entry = json.loads(line)
        return extract_metrics_from_log_entry(log_entry)
    except json.JSONDecodeError:
        pass
    
    # Try common log formats
    # Apache/Nginx combined log format
    apache_pattern = r'(?P<ip>\S+) \S+ \S+ \[(?P<timestamp>[^\]]+)\] "(?P<method>\S+) (?P<url>\S+) (?P<protocol>\S+)" (?P<status>\d+) (?P<size>\d+)'
    match = re.match(apache_pattern, line)
    if match:
        groups = match.groupdict()
        return {
            "service_id": "web_server",
            "timestamp": groups.get("timestamp", ""),
            "latency_ms": 0.0,
            "error_count": 1 if int(groups.get("status", 200)) >= 400 else 0,
            "request_count": 1
        }
    
    # Generic timestamp + level + message format
    generic_pattern = r'(?P<timestamp>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\s]*)\s+(?P<level>\w+)\s+(?P<message>.*)'
    match = re.match(generic_pattern, line)
    if match:
        groups = match.groupdict()
        level = groups.get("level", "").upper()
        return {
            "service_id": "application",
            "timestamp": groups.get("timestamp", ""),
            "latency_ms": 0.0,
            "error_count": 1 if level in ["ERROR", "CRITICAL", "FATAL"] else 0,
            "request_count": 1
        }
    
    return None

def extract_metrics_from_log_entry(log_entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract metrics from a structured log entry.
    """
    try:
        # Look for common metric fields
        service_id = (
            log_entry.get("service") or 
            log_entry.get("service_id") or 
            log_entry.get("application") or 
            log_entry.get("component", "unknown")
        )
        
        timestamp = (
            log_entry.get("timestamp") or 
            log_entry.get("time") or 
            log_entry.get("@timestamp") or 
            log_entry.get("ts", "")
        )
        
        # Extract latency if available
        latency_ms = 0.0
        if "latency" in log_entry:
            latency_ms = float(log_entry["latency"])
        elif "response_time" in log_entry:
            latency_ms = float(log_entry["response_time"])
        elif "duration" in log_entry:
            latency_ms = float(log_entry["duration"])
        
        # Determine if it's an error
        level = log_entry.get("level", "").upper()
        status_code = log_entry.get("status", log_entry.get("status_code", 200))
        
        error_count = 0
        if level in ["ERROR", "CRITICAL", "FATAL", "WARN"]:
            error_count = 1
        elif isinstance(status_code, int) and status_code >= 400:
            error_count = 1
        
        return {
            "service_id": str(service_id),
            "timestamp": str(timestamp),
            "latency_ms": latency_ms,
            "error_count": error_count,
            "request_count": 1
        }
        
    except Exception as e:
        logger.debug(f"Error extracting metrics from log entry: {str(e)}")
        return None

def ingest_log_file(file_path: str, ingestion_mode: str, line_range: Optional[Dict[str, int]] = None) -> List[Dict[str, Any]]:
    """
    Ingest data from a log file using streaming processing.
    """
    try:
        # Validate file path safety
        if not validate_path_safety(file_path):
            raise HTTPException(status_code=403, detail="Access denied: file path not allowed")
        
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        # Validate file size
        if not validate_file_size(file_path_obj):
            raise HTTPException(status_code=400, detail="File exceeds size limit")
        
        metrics = []
        line_number = 0
        max_lines_to_process = None
        
        # Validate line range if provided
        if ingestion_mode == "partial" and line_range:
            # First, quickly count lines to validate range
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                total_lines = sum(1 for _ in f)
            
            line_dict = line_range if isinstance(line_range, dict) else line_range.dict()
            validated_range = validate_line_range(line_dict, total_lines)
            if validated_range:
                max_lines_to_process = validated_range["end"]
                start_line = validated_range["start"]
            else:
                raise HTTPException(status_code=400, detail="Invalid line range")
        else:
            start_line = 0
            max_lines_to_process = LOG_PARSING["max_lines_per_batch"]
        
        # Stream process the file
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                # Skip lines until we reach the start line
                if line_number < start_line:
                    line_number += 1
                    continue
                
                # Stop if we've reached the maximum
                if max_lines_to_process and line_number >= max_lines_to_process:
                    break
                
                # Process the line
                metrics_data = parse_log_line(line)
                if metrics_data:
                    metrics.append(metrics_data)
                
                line_number += 1
        
        logger.info(f"Ingested {len(metrics)} metrics from {file_path} (processed {line_number} lines)")
        return metrics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ingesting log file {file_path}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error ingesting file: {str(e)}")

async def ingest_log_file_async(file_path: str, ingestion_mode: str, line_range: Optional[Dict[str, int]] = None) -> List[Dict[str, Any]]:
    """
    Async version of ingest_log_file using aiofiles.
    """
    try:
        # Validate file path safety
        if not validate_path_safety(file_path):
            raise HTTPException(status_code=403, detail="Access denied: file path not allowed")
        
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        # Validate file size
        if not validate_file_size(file_path_obj):
            raise HTTPException(status_code=400, detail="File exceeds size limit")
        
        metrics = []
        line_number = 0
        max_lines_to_process = None
        
        # Validate line range if provided
        if ingestion_mode == "partial" and line_range:
            # Count lines asynchronously for validation
            async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                total_lines = sum(1 for _ in await f.readlines())
            
            line_dict = line_range if isinstance(line_range, dict) else line_range.dict()
            validated_range = validate_line_range(line_dict, total_lines)
            if validated_range:
                max_lines_to_process = validated_range["end"]
                start_line = validated_range["start"]
            else:
                raise HTTPException(status_code=400, detail="Invalid line range")
        else:
            start_line = 0
            max_lines_to_process = LOG_PARSING["max_lines_per_batch"]
        
        # Stream process the file asynchronously
        async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            async for line in f:
                # Skip lines until we reach the start line
                if line_number < start_line:
                    line_number += 1
                    continue
                
                # Stop if we've reached the maximum
                if max_lines_to_process and line_number >= max_lines_to_process:
                    break
                
                # Process the line
                metrics_data = parse_log_line(line)
                if metrics_data:
                    metrics.append(metrics_data)
                
                line_number += 1
        
        logger.info(f"Ingested {len(metrics)} metrics from {file_path} (processed {line_number} lines)")
        return metrics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ingesting log file {file_path}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error ingesting file: {str(e)}")

@router.get("/logs/discover")
async def discover_logs(directory_path: str, file_pattern: str = "*.log"):
    """
    Discover available log files in a directory.
    """
    files = discover_log_files(directory_path, file_pattern)
    return {"files": [file.dict() for file in files]}

@router.post("/logs/ingest")
async def ingest_logs(request: LogIngestionRequest):
    """
    Ingest logs from specified directory and file pattern with async processing.
    """
    try:
        # Discover files
        files = discover_log_files(request.directory_path, request.file_pattern or "*.log")
        
        if not files:
            return {"message": "No files found matching the pattern", "processed_metrics": []}
        
        # Limit concurrent processing
        max_concurrent = PERFORMANCE["max_concurrent_files"]
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_file(file_info):
            async with semaphore:
                try:
                    # Use async file processing
                    line_range_dict = request.line_range.dict() if request.line_range else None
                    metrics = await ingest_log_file_async(
                        file_info.path, 
                        request.ingestion_mode.value, 
                        line_range_dict
                    )
                    
                    decisions = []
                    # Process each metric through the existing pipeline
                    for metric_data in metrics:
                        try:
                            # Convert to MetricData model
                            metric_obj = MetricData(**metric_data)
                            
                            # Process through existing pipeline
                            aggregated = aggregate_metrics(metric_data)
                            health_state = classify_health(aggregated)
                            decision = make_decision(health_state, aggregated)
                            
                            decisions.append(decision.dict())
                            
                            logger.info(
                                f"Processed log metrics for {metric_data['service_id']}", 
                                extra={
                                    "decision": decision.dict(),
                                    "service_id": metric_data['service_id'],
                                    "source_file": file_info.path
                                }
                            )
                            
                        except Exception as e:
                            logger.error(f"Error processing metric from {file_info.path}: {str(e)}")
                            continue
                    
                    return {
                        "file_path": file_info.path,
                        "metrics": metrics,
                        "decisions": decisions,
                        "processed_count": len(metrics)
                    }
                    
                except Exception as e:
                    logger.error(f"Error processing file {file_info.path}: {str(e)}")
                    return {
                        "file_path": file_info.path,
                        "error": str(e),
                        "metrics": [],
                        "decisions": [],
                        "processed_count": 0
                    }
        
        # Process files concurrently with timeout
        timeout = PERFORMANCE["timeout_seconds"]
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*[process_file(file_info) for file_info in files]),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=408, detail=f"Processing timeout after {timeout} seconds")
        
        # Aggregate results
        all_metrics = []
        all_decisions = []
        files_processed = 0
        
        for result in results:
            if "error" not in result:
                all_metrics.extend(result["metrics"])
                all_decisions.extend(result["decisions"])
                files_processed += 1
        
        return {
            "message": f"Processed {len(all_metrics)} metrics from {files_processed} files",
            "processed_metrics": len(all_metrics),
            "decisions": all_decisions,
            "files_processed": files_processed,
            "total_files_found": len(files)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in log ingestion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error in log ingestion: {str(e)}")

@router.post("/logs/ingest-file")
async def ingest_single_log_file(file_path: str, ingestion_mode: IngestionMode = IngestionMode.FULL, line_range: Optional[Dict[str, int]] = None):
    """
    Ingest logs from a single file using async processing.
    """
    try:
        # Use async file processing
        line_range_dict = line_range if isinstance(line_range, dict) else line_range.dict() if line_range else None
        metrics = await ingest_log_file_async(file_path, ingestion_mode.value, line_range_dict)
        decisions = []
        
        for metric_data in metrics:
            metric_obj = MetricData(**metric_data)
            aggregated = aggregate_metrics(metric_data)
            health_state = classify_health(aggregated)
            decision = make_decision(health_state, aggregated)
            decisions.append(decision.dict())
            
            logger.info(
                f"Processed log metrics for {metric_data['service_id']}", 
                extra={
                    "decision": decision.dict(),
                    "service_id": metric_data['service_id'],
                    "source_file": file_path
                }
            )
        
        return {
            "message": f"Processed {len(metrics)} metrics from {file_path}",
            "processed_metrics": len(metrics),
            "decisions": decisions
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ingesting single log file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error ingesting file: {str(e)}")
