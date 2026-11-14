import hashlib
import json
import os
import time
import tomllib
from pathlib import Path

import requests


class APIError(RuntimeError):
    def __init__(self, status, path):
        self.status = status
        super().__init__(f"HTTP {status} at {path}; check the Open WebUI container log")


class WebUI:
    def __init__(self, url):
        self.url = url.rstrip("/")
        self.session = requests.Session()

    def call(self, method, path, **kwargs):
        response = self.session.request(method, self.url + path, timeout=600, **kwargs)
        if not response.ok:
            raise APIError(response.status_code, path)
        return response.json()

    def login(self):
        result = self.call("POST", "/api/v1/auths/signin", json={
            "email": os.environ["WEBUI_ADMIN_EMAIL"],
            "password": os.environ["WEBUI_ADMIN_PASSWORD"],
        })
        self.session.headers["Authorization"] = f"Bearer {result['token']}"
        try:
            result = self.call("GET", "/api/v1/auths/api_key")
        except APIError as error:
            if error.status != 404:
                raise
            result = self.call("POST", "/api/v1/auths/api_key")
        return result["api_key"]


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def pull_model(url, model):
    existing = requests.post(url + "/api/show", json={"model": model}, timeout=30)
    if existing.ok:
        print(f"Using cached Ollama model {model}", flush=True)
        return
    if existing.status_code != 404:
        existing.raise_for_status()
    print(f"Preparing Ollama model {model} (first download can take a while)...", flush=True)
    with requests.post(url + "/api/pull", json={"model": model, "stream": True},
                       stream=True, timeout=(30, 1800)) as response:
        response.raise_for_status()
        last_status = None
        last_progress = None
        for line in response.iter_lines():
            if not line:
                continue
            event = json.loads(line)
            if "error" in event:
                raise RuntimeError(f"Ollama pull failed: {event['error']}")
            if event.get("status") != last_status:
                last_status = event.get("status")
                print(f"Ollama: {last_status}", flush=True)
                last_progress = None
            if event.get("total"):
                progress = int(10 * event.get("completed", 0) / event["total"]) * 10
                if progress != last_progress:
                    print(f"Ollama: {progress}%", flush=True)
                    last_progress = progress


def configure_model(api, base_model):
    try:
        current = api.call("GET", "/api/v1/models/model", params={"id": "avatar"})
    except APIError as error:
        if error.status not in (401, 404):
            raise
        current = None
    form = {
        "id": "avatar", "name": "Avatar", "base_model_id": base_model,
        "meta": {}, "params": {"think": False}, "access_grants": [],
    }
    if current:
        if current.get("base_model_id") == base_model:
            return
        form = {**current, "base_model_id": base_model}
    api.call("POST", "/api/v1/models/model/update" if current else "/api/v1/models/create", json=form)


def ensure_knowledge(api, state):
    knowledge_id = state.get("knowledge_id")
    if knowledge_id:
        try:
            api.call("GET", f"/api/v1/knowledge/{knowledge_id}")
            return knowledge_id
        except APIError as error:
            if error.status not in (400, 404):
                raise
    result = api.call("POST", "/api/v1/knowledge/create", json={
        "name": "ECA Avatar Knowledge", "description": "Managed from the local RAG folder",
        "access_grants": [],
    })
    state.clear()
    state["knowledge_id"] = result["id"]
    state["files"] = {}
    return result["id"]


def wait_for_file(api, file_id, timeout=900):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = api.call("GET", f"/api/v1/files/{file_id}/process/status")
        if result.get("status") == "completed":
            return
        if result.get("status") == "failed":
            raise RuntimeError(f"RAG file {file_id} could not be processed; check Open WebUI logs")
        time.sleep(2)
    raise TimeoutError(f"RAG file {file_id} is still processing")


def sync_rag(api, root, state, save):
    knowledge_id = state["knowledge_id"]
    base = f"/api/v1/knowledge/{knowledge_id}"
    # recover completed uploads after an interrupted sync
    remote = {}
    page = 1
    while True:
        result = api.call("GET", base + "/files", params={"page": page})
        items = result["items"]
        remote.update({item["filename"]: item["id"] for item in items})
        if not items or len(remote) >= result["total"]:
            break
        page += 1
    previous = state.setdefault("files", {})
    desired = {}
    available = {row["sha256"]: row["id"] for row in previous.values() if row["id"] in remote.values()}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink() or any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        name = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        upload_name = digest + path.suffix.lower()
        file_id = available.get(digest) or remote.get(upload_name)
        if not file_id:
            print(f"Importing RAG: {name}", flush=True)
            with path.open("rb") as stream:
                result = api.call("POST", "/api/v1/files/", files={"file": (upload_name, stream)})
            file_id = result["id"]
            wait_for_file(api, file_id)
            api.call("POST", base + "/file/add", json={"file_id": file_id})
        desired[name] = {"sha256": digest, "id": file_id}
        available[digest] = file_id
    # remove only files previously managed by this importer
    stale = {row["id"] for row in previous.values()} - {row["id"] for row in desired.values()}
    for file_id in stale:
        if file_id in remote.values():
            api.call("POST", base + "/file/remove", json={"file_id": file_id})
    state["files"] = desired
    save()
    print(f"RAG ready: {len(desired)} file(s)", flush=True)
    return bool(desired)


def provision():
    config_dir = Path(os.environ.get("ECA_CONFIG_DIR", "/config"))
    with (config_dir / "avatar.toml").open("rb") as stream:
        profile = tomllib.load(stream)
    state_dir = Path(os.environ.get("ECA_STATE_DIR", "/state"))
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "manifest.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    save = lambda: write_json(state_path, state)
    api = WebUI(os.environ["OPEN_WEBUI_URL"])
    api_key = api.login()
    base_model = profile["llm"]["base_model"]
    pull_model(os.environ["OLLAMA_URL"], base_model)
    configure_model(api, base_model)
    knowledge_id = ""
    rag = profile.get("rag", {})
    if rag.get("enabled", True):
        candidate = ensure_knowledge(api, state)
        save()
        if sync_rag(api, Path(os.environ.get("ECA_RAG_DIR", "/rag")), state, save):
            knowledge_id = candidate
    conversation = profile.get("conversation", {})
    values = {
        "OPEN_WEBUI_URL": os.environ["OPEN_WEBUI_URL"],
        "OPEN_WEBUI_API_KEY": api_key,
        "OPEN_WEBUI_KNOWLEDGE_ID": knowledge_id,
        "OPEN_WEBUI_RAG_TOP_K": str(rag.get("top_k", 5)),
        "OPEN_WEBUI_RAG_TIMEOUT": str(rag.get("timeout", 30)),
        "MAX_HISTORY_MESSAGES": str(conversation.get("max_history_messages", 4)),
        "ENHANCED": str(conversation.get("enhanced", True)).lower(),
    }
    # no secrets in stdout; publish config only after successful setup
    target = state_dir / "backend.env"
    temporary = target.with_suffix(".tmp")
    temporary.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(target)
    print("Backend configuration ready.", flush=True)


if __name__ == "__main__":
    provision()
