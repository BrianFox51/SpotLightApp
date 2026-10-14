from contextlib import asynccontextmanager
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app import models
from app.auth import router as auth_router
from app.config import settings
from app.database import Base, SessionLocal, engine
structlog.configure()
log = structlog.get_logger()
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    log.info("startup", env=settings.app_env)
    yield
app = FastAPI(
    title="Spotlight Server",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=False,
)
@app.get("/api/v1/health")
def health():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception:
        log.exception("health_check_failed")
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "error"},
        )
