import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import ask, datasets, misc
from app.config import settings
from app.db import Base, engine
from app.observability import request_middleware, setup_logging

setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Simple bootstrap. For production schema evolution, introduce Alembic migrations.
    Base.metadata.create_all(engine)
    logging.getLogger("app").info("started env=%s auth=%s engine=%s llm=%s", settings.env, settings.auth_mode, settings.query_engine, settings.llm_provider)
    yield


app = FastAPI(title="AI Data Analyst", version="1.0.0", lifespan=lifespan)
app.middleware("http")(request_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(datasets.router)
app.include_router(ask.router)
app.include_router(misc.router)


@app.get("/health")
def health():
    return {"status": "ok"}
