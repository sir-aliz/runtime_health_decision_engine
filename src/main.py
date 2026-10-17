from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .ingestion import router as ingestion_router
from .logger import logger
from .storage import init_db


@asynccontextmanager
async def lifespan(app):
    init_db()
    logger.info('RHDE Engine Started')
    yield


app = FastAPI(title='Runtime Health Decision Engine (RHDE)', version='1.1.0', lifespan=lifespan)
app.include_router(ingestion_router)
static_dir = Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=static_dir), name='static')


@app.get('/', include_in_schema=False)
@app.get('/incidents/{deployment_id}', include_in_schema=False)
def incident_page():
    return FileResponse(static_dir / 'index.html')


@app.get('/health')
def health_check():
    return {'status': 'ok'}
