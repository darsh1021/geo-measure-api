import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401  (registers tables on Base)
from app.api import files
from app.db import Base, engine
from app.errors import register_error_handlers
from app.schemas import ErrorResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Geospatial File Measurement API", lifespan=lifespan)
register_error_handlers(app)
app.include_router(
    files.router,
    prefix="/api/files",
    tags=["files"],
    responses={code: {"model": ErrorResponse} for code in (404, 409, 413, 415, 422, 500)},
)
