from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db
from .routers import auth, instructor, mentor, progress, quizzes

app = FastAPI(
    title="CyberPulse API",
    version="1.0.0",
    description="Backend for the CyberPulse cybersecurity learning platform.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "service": "cyberpulse-api"}


app.include_router(auth.router)
app.include_router(quizzes.router)
app.include_router(progress.router)
app.include_router(mentor.router)
app.include_router(instructor.router)
