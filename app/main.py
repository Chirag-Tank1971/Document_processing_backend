from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.documents import router as documents_router
from app.core.config import settings
from app.core.database import Base, engine
from app.core.logging import configure_logging

configure_logging()
Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name)

cors_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=settings.cors_allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents_router, prefix=settings.api_prefix, tags=["documents"])


@app.get("/health")
def healthcheck():
    return {"status": "ok"}
