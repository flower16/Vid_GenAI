"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.api import ingestion, compare, files, auth_routes, agent_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()           # create SQLite tables once on startup
    yield


app = FastAPI(title="SolarBillIQ", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Allow any localhost port (Vite may pick 5173, 5174, … if one is busy).
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(ingestion.router)
app.include_router(compare.router)
app.include_router(files.router)
app.include_router(agent_routes.router)


@app.get("/health")
def health():
    return {"status": "ok"}
