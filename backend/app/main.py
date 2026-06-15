import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import accounts, auth, bots
from app.core.config import settings
from app.core.db import init_db
from app.strategy.manager import bot_manager

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="AlgoTrading Bot", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(bots.router, prefix="/api/bots", tags=["bots"])


@app.on_event("startup")
def on_startup():
    init_db()
    # Resume any bots that were left enabled.
    bot_manager.resume_enabled()


@app.on_event("shutdown")
def on_shutdown():
    # Soft stop: leave resting orders so they resume on the next start.
    bot_manager.stop_all(cancel_orders=False)


@app.get("/health")
def health():
    return {"status": "ok"}
