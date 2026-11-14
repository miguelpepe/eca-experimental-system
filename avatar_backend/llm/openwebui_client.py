import json
import logging
import time

import requests

# import open web ui settings from config
from avatar_backend.config import (
    OPEN_WEBUI_API_KEY,
    OPEN_WEBUI_KNOWLEDGE_ID,
    OPEN_WEBUI_RAG_TIMEOUT,
    OPEN_WEBUI_RAG_TOP_K,  # number of knowledge base docs to retrieve
    OPEN_WEBUI_URL,
)

logger = logging.getLogger("llm")

_BASE = OPEN_WEBUI_URL  #  localhost or custom url
_CHAT_URL = f"{_BASE}/api/chat/completions"  # endpoint for chat answers
_RETRIEVAL_URL = (
    f"{_BASE}/api/v1/retrieval/query/collection"  # endpoint for rag retrieval
)
_SESSION = requests.Session()  # for same http connection

# headers for reqs
_HEADERS = {"Content-Type": "application/json"}
_HEADERS["Authorization"] = f"Bearer {OPEN_WEBUI_API_KEY}"  # api key for auth


# language lock prompt to ensure llm answers in wihpsers detected language (en or de)
def _language_lock(lang: str) -> str:
    answer = "German" if lang == "de" else "English"
    return (
        "HARD CONSTRAINT (OVERRIDES EVERYTHING):\n"
        f"You MUST answer EXCLUSIVELY in {answer}. \n"
        "If this rule is violated, the answer is INVALID.\n"
    )


# build rag query from recent user and assistant messages
def _retrieval_query(messages: list[dict]) -> str:
    recent_messages = messages[-3:]  # last 3 messages for context
    query_parts = []

    # add n recent user or assistantn messages
    for message in recent_messages:
        if message["role"] in ("user", "assistant"):
            query_parts.append(message["content"])

    return " ".join(query_parts).strip()


# fetch rag context from open webui collection
def _fetch_rag_context(query: str) -> str:
    # http post to retrieval endpoint
    resp = _SESSION.post(
        _RETRIEVAL_URL,  # endpoint for retrieval
        json={
            "collection_names": [OPEN_WEBUI_KNOWLEDGE_ID],  # collection to query
            "query": query,
            "k": OPEN_WEBUI_RAG_TOP_K,  # best k docs to return
        },
        headers=_HEADERS,
        timeout=OPEN_WEBUI_RAG_TIMEOUT,
    )
    resp.raise_for_status()

    # parse response and extract documents
    response_data = resp.json()
    documents = response_data["documents"][0]

    # concat docs with sepearator
    context_parts = []
    for document in documents:
        if document:
            context_parts.append(document.strip())

    context = " --- ".join(context_parts)
    if not context:
        return ""

    rag_instruction = (
        "The following information inside <context> is your own knowledge. "
        "Use it naturally to answer. Never mention the context, sources, documents, "
        "files, citations, or a knowledge base, and never use bracketed reference "
        "numbers such as [1]. If the needed information is not in your knowledge and "
        "you do not know it reliably, say plainly that you do not have reliable "
        "information on that."
    )
    # combine instruction and context for llm prompt
    return f"{rag_instruction}\n<context>\n{context}\n</context>"


# builds complete prompt for llm
def _build_messages(messages: list[dict], lang: str) -> list[dict]:
    chat = [dict(m) for m in messages]  # copy of msgs to modify

    # lang lock before system prompt
    chat[0]["content"] = _language_lock(lang) + "\n\n" + chat[0]["content"]

    # if rag enabled, fetch context
    if OPEN_WEBUI_KNOWLEDGE_ID:
        t = time.time()
        # build retrival query and fetch context
        context = _fetch_rag_context(_retrieval_query(chat))
        if context:
            # add context to system prompt for llm
            chat[0]["content"] += "\n\n" + context
        logger.info("[RAG] fetched %.3fs", time.time() - t)
    # return chat with modified system prompt
    return chat


# yield deltas from streaming response
def _iter_deltas(resp):
    # iterate over lines in streaming response
    for raw in resp.iter_lines():

        # skip empty lines
        if not raw:
            continue

        line = raw.decode("utf-8")  # decode bytes to string

        # only lines with "data:"
        if not line.startswith("data: "):
            continue

        # remove data prefix
        data = line.removeprefix("data: ").strip()

        # done = end of stream
        if data == "[DONE]":
            break

        chunk = json.loads(data)  # parse json to dict
        # extract content delta from response chunk
        delta = chunk["choices"][0]["delta"].get("content")

        # yield delta if existis
        if delta:
            yield delta


# stream llm response from open webui
def stream_llm(messages: list[dict], lang: str, llm_config):
    # request body
    payload = {
        "model": llm_config["model"],
        "messages": _build_messages(messages, lang),  # build prompt
        "stream": True,  # enable streaming response
        "stop": llm_config["stop"],
    }

    logger.info("[LLM] start lang=%s model=%s", lang, llm_config["model"])
    t0 = time.time()  # measure time for llm response

    # send http post to chat endpoint with payload and headers
    resp = _SESSION.post(
        _CHAT_URL,
        json=payload,
        headers=_HEADERS,
        timeout=llm_config["timeout_seconds"],
        stream=True,
    )
    resp.raise_for_status()

    # iterate over streaming response and yield deltas
    for delta in _iter_deltas(resp):
        yield delta

    logger.info("[LLM] done %.2fs", time.time() - t0)
