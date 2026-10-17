import requests
import time
import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4

BASE_URL = "http://localhost:8000"

def simulate_traffic():
    run_id = uuid4().hex[:8]
    services = [f"{name}-{run_id}" for name in ["order-service", "payment-service", "user-service"]]
    start = datetime.now(timezone.utc) - timedelta(minutes=20)
    
    # Scenarios
    scenarios = [
        {"latency": 100, "error_count": 0, "request_count": 100},   # Healthy
        {"latency": 600, "error_count": 5, "request_count": 100},   # Degraded (Latency)
        {"latency": 200, "error_count": 15, "request_count": 100},  # Critical (Error Rate)
    ]
    
    print(f"Targeting {BASE_URL}...")
    
    try:
        # Check health
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        if resp.status_code != 200:
            print("API is not healthy")
            return

        for i in range(10):
            service = random.choice(services)
            scenario = random.choice(scenarios)
            
            payload = {
                "service_id": service,
                "timestamp": (start + timedelta(minutes=i)).isoformat(),
                "interval_seconds": 60,
                "latency_ms": scenario["latency"],
                "error_count": scenario["error_count"],
                "request_count": scenario["request_count"]
            }
            
            try:
                resp = requests.post(f"{BASE_URL}/metrics", json=payload, timeout=5)
                resp.raise_for_status()
                data = resp.json()
                print(f"[{service}] Input: lat={scenario['latency']}, err={scenario['error_count']} -> Result: {data['health_state']} | Action: {data['action']}")
            except Exception as e:
                print(f"Request failed: {e}")
                
            time.sleep(0.5)
            
    except requests.exceptions.ConnectionError:
        print("Could not connect to server. Is it running?")

if __name__ == "__main__":
    simulate_traffic()
