# Development Process & Technical Reflection
## Runtime Health Decision Engine (RHDE)

### 1. Initial Analysis & Decomposition
Upon receiving the request, I analyzed the core problem: **automating the interpretation of operational metrics**.

The key insight was to break the problem into a linear data processing pipeline:
1.  **Input:** Raw messy data (counters, latencies).
2.  **Processing:** Normalization (rates), Classification (thresholds), Decision (business logic).
3.  **Output:** Structured data (logs/JSON) for downstream consumption.

I deliberately chose a **Modular Monolith** approach for the MVP. While microservices are a valid target *deployment* model for distributed systems, the RHDE engine itself should be a self-contained unit to ensure low latency logic processing.

### 2. Implementation Strategy

#### Phase 1: The Core Domain (Logic First)
I started by implementing the pure logic modules (`classification.py` and `decision.py`) *before* the API.
*   **Why?** This allows for testing the business rules without the complexity of a web server.
*   **Design Choice:** I used pure functions where possible. `classify_health(metrics)` takes a dictionary and returns a string. It has no side effects, making it trivial to test and reason about.

#### Phase 2: Configuration & Flexibility
I extracted thresholds into `config.py`.
*   **Reasoning:** Thresholds (what defines "High Latency") change frequently. Hardcoding them in logic files would be a maintenance nightmare.
*   **Data Structure:** Nested dictionaries allow for future per-service configuration overrides (e.g., "payment-service" might be stricter than "image-service").

#### Phase 3: The Interface (FastAPI)
I chose **FastAPI** over Flask or Django.
*   **Type Safety:** Pydantic models (`MetricData`) ensure that we fail fast if invalid data is sent, protecting the core logic.
*   **Async Support:** Essential for future extensibility if we add I/O bound DB calls or external webhooks.
*   **Docs:** Automatic Swagger UI generation is a huge plus for SRE teams exploring the API.

#### Phase 4: Observability
I implemented structured JSON logging (`logger.py`).
*   **Philosophy:** "Logs are data." By printing JSON to stdout, we enable easy ingestion by tools like ELK, Splunk, or Datadog without complex parsing rules.

### 3. Challenges & Adaptations
**Challenge:** The development environment lacked some specific python package binaries in the system path (`uvicorn` not found).
**Adaptation:**
*   Instead of relying on the auto-run tools which failed, I pivoted to a **Manual Verification** strategy.
*   I created a robust simulation script (`simulate_traffic.py`) that acts as a mock client. This allows you to verify the entire system end-to-end on your local machine with a single command, bypassing the environment limitations I faced.

### 4. Future Roadmap Thoughts
Reflecting on the MVP, the next critical steps for a production validation would be:
1.  **State Management:** Currently, we calculate error rates per request batch. Real-world systems need "Rolling Windows" (e.g., error rate over the last 5 minutes). This would require a store like Redis.
2.  **Feedback Loops:** The decision engine outputs a "Decision", but does not yet *execute* it. Adding a "Webhooks" module to actually trigger the retry/fallback mechanisms would complete the loop.

### 5. Conclusion
This project demonstrates how to build a reliable reliability tool. By keeping the core logic decoupled from the delivery mechanism (API), the system ensures fast, testable, and deterministic decisions—critical traits for any SRE tool.
