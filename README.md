# Runtime Health Decision Engine (RHDE)

RHDE is a system to ingest metrics, classify service health, and recommend actionable decisions.

## Features
- **Ingestion**: Accepts metrics via HTTP API.
- **Classification**: Determines Healthy/Degraded/Critical states based on thresholds.
- **Decision Engine**: Recommends actions (Retry, Alert, Maintain).
- **Logging**: Structured JSON logging.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the server:
   ```bash
   uvicorn src.main:app --reload
   ```

3. Run the traffic simulator (in another terminal):
   ```bash
   python tests/simulate_traffic.py
   ```

## Configuration
Adjust thresholds in `src/config.py`.
