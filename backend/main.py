"""
Personal AI Agent — FastAPI Backend
Connects the dashboard UI to Ollama (local LLMs) with hybrid cloud fallback.
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import AsyncGenerator, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Personal AI Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_BASE = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "deepseek-coder:7b")

# In-memory log buffer (last 200 lines)
log_buffer: list[dict] = []
session_stats = {"tokens": 0, "tasks": 0, "started": datetime.now().isoformat()}


def add_log(level: str, message: str):
    entry = {"time": datetime.now().strftime("%H:%M:%S"), "level": level, "msg": message}
    log_buffer.append(entry)
    if len(log_buffer) > 200:
        log_buffer.pop(0)
    print(f"[{entry['time']}] [{level.upper()}] {message}")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    model: str = DEFAULT_MODEL
    system_prompt: Optional[str] = None
    stream: bool = True

class ApiKeyRequest(BaseModel):
    provider: str  # anthropic | openai | google
    key: str

class PullModelRequest(BaseModel):
    model: str

class RoutingConfig(BaseModel):
    prefer_local_for_code: bool = True
    cloud_for_vision: bool = True
    cloud_for_complex: bool = True
    cloud_fallback: bool = False


# ---------------------------------------------------------------------------
# Health & status
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    ollama_ok = await _check_ollama()
    return {
        "status": "ok",
        "ollama": ollama_ok,
        "timestamp": datetime.now().isoformat(),
        "session": session_stats,
    }


@app.get("/status")
async def status():
    ollama_ok = await _check_ollama()
    models = await _list_local_models() if ollama_ok else []
    return {
        "ollama_running": ollama_ok,
        "ollama_url": OLLAMA_BASE,
        "models": models,
        "default_model": DEFAULT_MODEL,
        "logs": log_buffer[-20:],
        "stats": session_stats,
    }


async def _check_ollama() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{OLLAMA_BASE}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


async def _list_local_models() -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{OLLAMA_BASE}/api/tags")
            data = r.json()
            return [
                {
                    "name": m["name"],
                    "size_gb": round(m.get("size", 0) / 1e9, 1),
                    "modified": m.get("modified_at", ""),
                }
                for m in data.get("models", [])
            ]
    except Exception as e:
        add_log("error", f"Could not list models: {e}")
        return []


# ---------------------------------------------------------------------------
# Models management
# ---------------------------------------------------------------------------

@app.get("/models")
async def list_models():
    models = await _list_local_models()
    add_log("info", f"Listed {len(models)} local models")
    return {"models": models}


@app.post("/models/pull")
async def pull_model(req: PullModelRequest):
    """Stream pull progress from Ollama."""
    add_log("info", f"Pulling model: {req.model}")

    async def _stream():
        try:
            async with httpx.AsyncClient(timeout=600) as client:
                async with client.stream(
                    "POST",
                    f"{OLLAMA_BASE}/api/pull",
                    json={"name": req.model},
                ) as resp:
                    async for line in resp.aiter_lines():
                        if line:
                            yield line + "\n"
            add_log("ok", f"Model {req.model} pulled successfully")
        except Exception as e:
            add_log("error", f"Pull failed: {e}")
            yield json.dumps({"error": str(e)}) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


@app.delete("/models/{model_name}")
async def delete_model(model_name: str):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.delete(
                f"{OLLAMA_BASE}/api/delete",
                json={"name": model_name},
            )
            add_log("ok", f"Deleted model: {model_name}")
            return {"deleted": model_name, "status": r.status_code}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Chat (streaming + non-streaming)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_DEFAULT = """You are a personal AI agent running locally on the user's laptop.
You can help with coding, file management, automation, app building, and general tasks.
You have access to the local filesystem and can execute code via Open Interpreter.
Be concise, helpful, and always explain what you are doing step by step.
When writing code, always include brief comments explaining key sections."""


@app.post("/chat")
async def chat(req: ChatRequest):
    system = req.system_prompt or SYSTEM_PROMPT_DEFAULT
    add_log("info", f"Chat request — model: {req.model} | msg: {req.message[:60]}...")
    session_stats["tasks"] += 1

    if req.stream:
        return StreamingResponse(
            _stream_ollama(req.model, req.message, system),
            media_type="text/event-stream",
        )
    else:
        reply = await _complete_ollama(req.model, req.message, system)
        return {"reply": reply, "model": req.model}


async def _stream_ollama(model: str, message: str, system: str) -> AsyncGenerator[str, None]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ],
        "stream": True,
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST", f"{OLLAMA_BASE}/api/chat", json=payload
            ) as resp:
                if resp.status_code != 200:
                    yield f"data: {json.dumps({'error': f'Ollama returned {resp.status_code}'})}\n\n"
                    return
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            session_stats["tokens"] += len(token.split())
                            yield f"data: {json.dumps({'token': token})}\n\n"
                        if chunk.get("done"):
                            yield f"data: {json.dumps({'done': True})}\n\n"
                    except json.JSONDecodeError:
                        continue
        add_log("ok", "Stream completed")
    except httpx.ConnectError:
        msg = "Cannot connect to Ollama. Is it running? Run: ollama serve"
        add_log("error", msg)
        yield f"data: {json.dumps({'error': msg})}\n\n"
    except Exception as e:
        add_log("error", f"Stream error: {e}")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


async def _complete_ollama(model: str, message: str, system: str) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ],
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{OLLAMA_BASE}/api/chat", json=payload)
        data = r.json()
        return data.get("message", {}).get("content", "")


# ---------------------------------------------------------------------------
# Conversation with history
# ---------------------------------------------------------------------------

class ConversationRequest(BaseModel):
    messages: list[dict]   # [{"role": "user"|"assistant", "content": "..."}]
    model: str = DEFAULT_MODEL
    system_prompt: Optional[str] = None

@app.post("/chat/conversation")
async def conversation(req: ConversationRequest):
    """Multi-turn conversation — send full message history."""
    system = req.system_prompt or SYSTEM_PROMPT_DEFAULT
    payload = {
        "model": req.model,
        "messages": [{"role": "system", "content": system}] + req.messages,
        "stream": True,
    }
    add_log("info", f"Conversation ({len(req.messages)} turns) — model: {req.model}")

    return StreamingResponse(
        _stream_raw(payload),
        media_type="text/event-stream",
    )


async def _stream_raw(payload: dict) -> AsyncGenerator[str, None]:
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", f"{OLLAMA_BASE}/api/chat", json=payload) as resp:
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield f"data: {json.dumps({'token': token})}\n\n"
                        if chunk.get("done"):
                            yield f"data: {json.dumps({'done': True})}\n\n"
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


# ---------------------------------------------------------------------------
# API key management (env-based, no disk storage of keys)
# ---------------------------------------------------------------------------

_api_keys: dict[str, str] = {}

@app.post("/keys")
async def save_key(req: ApiKeyRequest):
    _api_keys[req.provider] = req.key
    os.environ[f"{req.provider.upper()}_API_KEY"] = req.key
    add_log("ok", f"{req.provider} API key saved to session")
    return {"saved": req.provider}


@app.get("/keys")
async def list_keys():
    return {"configured": list(_api_keys.keys())}


# ---------------------------------------------------------------------------
# System metrics (lightweight — no psutil required for basic use)
# ---------------------------------------------------------------------------

@app.get("/metrics")
async def metrics():
    """Return lightweight system stats using cross-platform shell commands."""
    import platform
    result = {"platform": platform.system(), "timestamp": datetime.now().isoformat()}

    try:
        if platform.system() == "Darwin":  # macOS
            mem = subprocess.check_output(["vm_stat"], text=True)
            result["memory_raw"] = mem[:200]
        elif platform.system() == "Linux":
            with open("/proc/meminfo") as f:
                lines = f.readlines()
            mem_info = {l.split(":")[0]: int(l.split()[1]) for l in lines if ":" in l}
            total = mem_info.get("MemTotal", 0)
            avail = mem_info.get("MemAvailable", 0)
            used = total - avail
            result["ram_total_gb"] = round(total / 1e6, 1)
            result["ram_used_gb"] = round(used / 1e6, 1)
            result["ram_pct"] = round((used / total) * 100) if total else 0
    except Exception as e:
        result["metrics_error"] = str(e)

    result["session"] = session_stats
    result["log_lines"] = len(log_buffer)
    return result


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

@app.get("/logs")
async def get_logs(last: int = 50):
    return {"logs": log_buffer[-last:]}


@app.delete("/logs")
async def clear_logs():
    log_buffer.clear()
    return {"cleared": True}


# ---------------------------------------------------------------------------
# Agent task runner (Open Interpreter bridge)
# ---------------------------------------------------------------------------

class AgentTask(BaseModel):
    task: str
    model: str = DEFAULT_MODEL
    safe_mode: bool = True  # sandboxed by default

@app.post("/agent/run")
async def run_agent_task(req: AgentTask):
    """
    Run a task via Open Interpreter (must be installed: pip install open-interpreter).
    Returns streamed output.
    """
    add_log("info", f"Agent task: {req.task[:80]}")
    session_stats["tasks"] += 1

    async def _run():
        try:
            import interpreter  # open-interpreter
            interpreter.llm.model = f"ollama/{req.model}"
            interpreter.llm.api_base = OLLAMA_BASE
            interpreter.auto_run = not req.safe_mode
            interpreter.llm.supports_functions = False

            for chunk in interpreter.chat(req.task, stream=True, display=False):
                if isinstance(chunk, dict):
                    yield f"data: {json.dumps(chunk)}\n\n"
                else:
                    yield f"data: {json.dumps({'output': str(chunk)})}\n\n"

            add_log("ok", f"Agent task complete: {req.task[:40]}")
            yield f"data: {json.dumps({'done': True})}\n\n"

        except ImportError:
            msg = "Open Interpreter not installed. Run: pip install open-interpreter"
            add_log("warn", msg)
            yield f"data: {json.dumps({'error': msg, 'install': 'pip install open-interpreter'})}\n\n"
        except Exception as e:
            add_log("error", f"Agent task failed: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(_run(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    add_log("ok", "Personal AI Agent backend started")
    ok = await _check_ollama()
    if ok:
        models = await _list_local_models()
        add_log("ok", f"Ollama connected — {len(models)} model(s) available")
        for m in models:
            add_log("info", f"  • {m['name']} ({m['size_gb']} GB)")
    else:
        add_log("warn", "Ollama not running — start it with: ollama serve")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
