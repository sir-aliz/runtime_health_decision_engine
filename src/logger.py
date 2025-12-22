import logging
import sys
import json

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "level": record.levelname,
            "message": record.getMessage(),
            "time": self.formatTime(record, self.datefmt),
            "name": record.name
        }
        if hasattr(record, "decision"):
            log_record["decision"] = record.decision
        if hasattr(record, "service_id"):
            log_record["service_id"] = record.service_id
            
        return json.dumps(log_record)

def setup_logger():
    logger = logging.getLogger("rhde")
    logger.setLevel(logging.INFO)
    
    handler = logging.StreamHandler(sys.stdout)
    formatter = JsonFormatter()
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    return logger

logger = setup_logger()
