from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from paper_agent.api.routes.chat import router as chat_router
from paper_agent.api.routes.conferences import router as conferences_router
from paper_agent.api.routes.health import router as health_router
from paper_agent.api.routes.papers import router as papers_router
from paper_agent.config import get_settings
from paper_agent.db import initialize_database

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await initialize_database()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(papers_router)
app.include_router(conferences_router)
app.include_router(chat_router)
