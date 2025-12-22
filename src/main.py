from fastapi import FastAPI
from .ingestion import router as ingestion_router
from .logger import logger

app = FastAPI(title="Runtime Health Decision Engine (RHDE)", version="1.0.0")

app.include_router(ingestion_router)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.on_event("startup")
async def startup_event():
    logger.info("RHDE Engine Started")
