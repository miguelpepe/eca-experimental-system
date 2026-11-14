import os
from pathlib import Path

from dotenv import load_dotenv

# load env variables from .env file
load_dotenv()


# how many past messages include in conversation history
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "4"))

# experiment conditon
ENHANCED = os.getenv("ENHANCED", "false").lower() == "true"

# warmup toglle to reduce latency for first request
WARMUP = os.getenv("WARMUP", "false").lower() == "true"


# open web ui config
OPEN_WEBUI_URL = os.getenv("OPEN_WEBUI_URL", "http://localhost:3000")
OPEN_WEBUI_API_KEY = os.getenv("OPEN_WEBUI_API_KEY", "")
OPEN_WEBUI_KNOWLEDGE_ID = os.getenv("OPEN_WEBUI_KNOWLEDGE_ID", "")  # RAG
OPEN_WEBUI_RAG_TOP_K = int(os.getenv("OPEN_WEBUI_RAG_TOP_K", "5"))
OPEN_WEBUI_RAG_TIMEOUT = int(os.getenv("OPEN_WEBUI_RAG_TIMEOUT", "10"))


# Project paths
BASE_DIR = Path(__file__).resolve().parents[1]  # path to avatar_backend
PROJECT_ROOT = BASE_DIR.parent  # project root
UPLOAD_DIR = PROJECT_ROOT / "uploads"  # dir to store uploaded files
