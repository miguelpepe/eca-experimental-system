import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from avatar_backend.api.respond import router as respond_router
from avatar_backend.config import ENHANCED
from avatar_backend.config.conditions import build_condition
from avatar_backend.pipeline.conversation_pipeline import ConversationPipeline
from avatar_backend.warmup import run_warmup

# logging for structured output
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)


# define lifespan for FastAPI App
@asynccontextmanager
async def lifespan(app: FastAPI):

    # FastAPI Startup
    logging.getLogger("main").info("[APP] startup")

    # add global objects to FastAPI App
    app.state.condition = build_condition(
        ENHANCED
    )  # active experimental condition at startup
    app.state.conversation_pipeline = (
        ConversationPipeline()
    )  # manages conversation state and processing
    app.state.active_response = (
        None  # currently running response task
    )

    # running warmup with models in external thread
    threading.Thread(
        target=run_warmup,
        daemon=True,
    ).start()

    yield

    # FastAPI shutdown

    logging.getLogger("main").info("[APP] shutdown")


# create FastAPI App with defined lifespan
app = FastAPI(lifespan=lifespan)

# activate cors to connect with unreal engine frontend (maybe configure for specific origins in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# WebSocket /ws: receive base64 audio and stream spoken response events
app.include_router(respond_router)


@app.get("/health")
async def health():
    return {"status": "ok", "condition": app.state.condition["id"]}
