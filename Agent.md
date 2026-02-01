# Runtime Health Decision Engine (RHDE) Agent

## Overview
RHDE is an intelligent agent that monitors service health metrics, classifies operational states, and recommends automated actions to maintain system reliability.

## Core Capabilities

### 🔄 **Metrics Ingestion**
- Accepts real-time service metrics via HTTP API
- Processes: latency, error counts, request counts
- Input validation through Pydantic models
- Structured JSON logging for all inputs

### 🧠 **Health Classification**
- Automated classification into three states:
  - **Healthy**: Service operating within normal parameters
  - **Degraded**: Service showing performance issues
  - **Critical**: Service experiencing severe problems
- Configurable thresholds per metric type
- Rule-based logic for consistent decision making

### ⚡ **Decision Engine**
- Generates actionable recommendations:
  - **Healthy** → No Action Required
  - **Degraded** → Monitor/Retry operations
  - **Critical** → Alert/Fallback procedures
- Sub-200ms decision processing time
- Stateless architecture for scalability

### 📊 **Technical Architecture**
- **Framework**: FastAPI with async support
- **Design**: Modular monolith for low-latency processing
- **Language**: Python with type safety
- **Logging**: Structured JSON for observability
- **Configuration**: External threshold management

## Integration Points

### API Endpoints
```
POST /metrics
Content-Type: application/json

{
  "service_id": string,
  "latency": float,
  "error_count": integer,
  "request_count": integer
}
```

### Configuration
Thresholds managed in `src/config.py`:
- Response time limits
- Error rate thresholds
- Service-specific overrides supported

### Output Format
All decisions logged as structured JSON:
```json
{
  "timestamp": "ISO8601",
  "service_id": "string",
  "metrics": {...},
  "classification": "Healthy|Degraded|Critical",
  "decision": "Action recommendation",
  "processing_time_ms": float
}
```

## Operational Benefits

### 🎯 **Automation**
- Eliminates manual dashboard monitoring
- Reduces human interpretation errors
- Enables 24/7 automated health assessment

### ⏱️ **Speed**
- Immediate health classification
- Rapid decision generation
- Reduced Mean Time To Resolution (MTTR)

### 🔍 **Observability**
- Complete audit trail of all decisions
- Structured logging for easy ingestion
- Foundation for post-mortem analysis

## Deployment Considerations

### Current State
- Stateless MVP implementation
- In-memory processing
- Container-ready Python application

### Future Enhancements
- Redis integration for rolling windows
- Webhook execution for automated actions
- ML-based anomaly detection
- Multi-service orchestration

## Usage

### Start the Agent
```bash
pip install -r requirements.txt
uvicorn src.main:app --reload
```

### Test with Traffic Simulator
```bash
python tests/simulate_traffic.py
```

## Business Value
- **Operational Efficiency**: Frees SRE teams from routine monitoring
- **Reliability**: Prevents cascading failures through early detection
- **Foundation**: Establishes baseline for future AI-driven operations
- **Scalability**: Handles growing service ecosystems without human bottlenecks

This agent serves as the intelligent decision-making layer in modern distributed systems, transforming raw telemetry into actionable operational intelligence.