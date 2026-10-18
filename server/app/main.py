from contextlib import asynccontextmanager
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from app import models
from app.auth import router as auth_router
from app.moderation import router as moderation_router
from app.favorites import router as favorites_router
from app.submissions import router as submissions_router
from app.profile import router as profile_router
from app.community import router as community_router
from app.rate_limit import limiter
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
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(favorites_router, prefix="/api/v1", tags=["favorites"])
app.include_router(submissions_router, prefix="/api/v1", tags=["submissions"])
app.include_router(moderation_router, prefix="/api/v1", tags=["moderation"])
app.include_router(profile_router, prefix="/api/v1", tags=["profile"])
app.include_router(community_router, prefix="/api/v1", tags=["community"])
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
