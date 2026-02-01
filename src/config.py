
# Service Health Thresholds
THRESHOLDS = {
    "default": {
        "latency_critical_ms": 1000,
        "latency_degraded_ms": 500,
        "error_rate_critical": 0.10,
        "error_rate_degraded": 0.05
    }
}

# Log Parsing Configuration
LOG_PARSING = {
    "default_file_patterns": ["*.log", "*.txt", "*.out"],
    "max_file_size_mb": 100,
    "max_lines_per_batch": 10000,
    "supported_formats": ["json", "apache", "nginx", "generic"],
    "field_mappings": {
        "service_fields": ["service", "service_id", "application", "component"],
        "timestamp_fields": ["timestamp", "time", "@timestamp", "ts", "datetime"],
        "latency_fields": ["latency", "response_time", "duration", "elapsed"],
        "status_fields": ["status", "status_code", "http_status"],
        "error_levels": ["ERROR", "CRITICAL", "FATAL", "WARN", "WARNING"]
    }
}

# Security Configuration
SECURITY = {
    "allowed_base_paths": ["/var/log", "/tmp", "/logs"],  # Only allow these base directories
    "max_path_depth": 10,  # Maximum directory depth
    "blocked_patterns": ["../", "..\\", "~", "/etc", "/sys", "/proc"],  # Block dangerous paths
}

# Performance Configuration
PERFORMANCE = {
    "streaming_chunk_size": 8192,  # Bytes to read at a time
    "max_concurrent_files": 10,  # Max files to process simultaneously
    "timeout_seconds": 300,  # Max processing time per request
}
