"""Shop Helper service: puts a read-only AI helper inside Bay Log without changing Bay Log.

One port, one hostname:
  /helper/*  -> this service (chat, health, panel assets)
  anything else -> reverse-proxied to Bay Log, with the panel <script> injected into its page

The chat loop: local model (Ollama) <-> baylog-mcp tools (stdio) <-> Bay Log API.
Progress streams back as NDJSON lines so the panel can show each tool call live:
  {"type":"step","tool":"get_ticket","args":{...}}  ...  {"type":"answer","text":"..."}

Env: BAYLOG_API (http://127.0.0.1:8080), OLLAMA_URL (http://127.0.0.1:11434),
     MODEL (qwen2.5:7b), HELPER_NUM_CTX (4096)
Run: uvicorn helper:app --host 0.0.0.0 --port 8090
"""
import asyncio
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent
BAYLOG = os.environ.get("BAYLOG_API", "http://127.0.0.1:8080").rstrip("/")
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.environ.get("MODEL", "qwen2.5:7b")
NUM_CTX = int(os.environ.get("HELPER_NUM_CTX", "4096"))
SYSTEM = (HERE / "prompts" / "shop-helper.md").read_text()
MAX_ROUNDS = 4
PANEL_TAG = b'<script src="/helper/static/shop-helper.js" defer></script>'
HOP = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade",
       "proxy-authorization", "proxy-authenticate", "content-length", "content-encoding", "host"}

proxy_client: httpx.AsyncClient | None = None


async def warm_model():
    """Load the model into RAM at startup so the first question isn't the slow one."""
    try:
        async with httpx.AsyncClient(timeout=600) as c:
            await c.post(f"{OLLAMA}/api/generate", json={"model": MODEL, "prompt": "ok", "stream": False,
                                                         "keep_alive": "60m", "options": {"num_predict": 1}})
    except Exception as e:  # never block startup on the model
        print(f"[helper] model warm-up skipped: {e}", file=sys.stderr)


@asynccontextmanager
async def lifespan(_app):
    global proxy_client
    proxy_client = httpx.AsyncClient(base_url=BAYLOG, timeout=60)
    task = asyncio.create_task(warm_model())
    yield
    task.cancel()
    await proxy_client.aclose()


app = FastAPI(title="Shop Helper", lifespan=lifespan)


# ---------------------------------------------------------------- helper API
class Turn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=4000)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    ticket_id: str | None = Field(default=None, max_length=20)
    history: list[Turn] = Field(default_factory=list, max_length=12)


@app.get("/helper/health")
async def health():
    out = {"model": MODEL, "baylog": "down", "ollama": "down", "model_loaded": False}
    async with httpx.AsyncClient(timeout=5) as c:
        try:
            out["baylog"] = (await c.get(f"{BAYLOG}/api/health")).json().get("status", "?")
        except Exception:
            pass
        try:
            tags = (await c.get(f"{OLLAMA}/api/tags")).json().get("models", [])
            out["ollama"] = "ok" if any(m["name"] in (MODEL, MODEL + ":latest") for m in tags) else f"model {MODEL} not pulled"
            ps = (await c.get(f"{OLLAMA}/api/ps")).json().get("models", [])
            out["model_loaded"] = any(m["name"] in (MODEL, MODEL + ":latest") for m in ps)
        except Exception:
            pass
    return out


@app.get("/helper/static/{name}")
async def panel_asset(name: str):
    f = (HERE / "static" / name).resolve()
    if f.parent != (HERE / "static").resolve() or not f.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(f, headers={"Cache-Control": "no-cache"})


def _step_label(name: str, args: dict) -> str:
    return {"get_ticket": f"Opened {args.get('ticket_id', '?')}",
            "search_tickets": f"Searched tickets: {args.get('query', '')}",
            "get_board": "Checked the shop board",
            "search_kb": f"Searched shop procedures: {args.get('query', '')}"}.get(name, name)


async def chat_events(body: ChatIn):
    t0 = time.monotonic()
    def line(obj): return (json.dumps(obj) + "\n").encode()

    system = SYSTEM + (f"\n\nOpen ticket on the student's screen: {body.ticket_id}" if body.ticket_id else
                       "\n\nNo ticket is open on the student's screen.")
    msgs = [{"role": "system", "content": system}] + [t.model_dump() for t in body.history[-8:]] + \
           [{"role": "user", "content": body.message}]
    params = StdioServerParameters(command=sys.executable, args=[str(HERE / "baylog_mcp.py")],
                                   env={**os.environ, "BAYLOG_API": BAYLOG})
    try:
        async with stdio_client(params, errlog=open(os.devnull, "w")) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            tools = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                        "parameters": t.inputSchema}}
                     for t in (await s.list_tools()).tools]
            yield line({"type": "status", "text": "Thinking…"})
            async with httpx.AsyncClient(timeout=600) as oc:
                for _ in range(MAX_ROUNDS):
                    res = await oc.post(f"{OLLAMA}/api/chat", json={
                        "model": MODEL, "messages": msgs, "tools": tools, "stream": False, "keep_alive": "60m",
                        "options": {"temperature": 0.2, "num_ctx": NUM_CTX}})
                    res.raise_for_status()
                    m = res.json()["message"]
                    msgs.append(m)
                    calls = m.get("tool_calls") or []
                    if not calls:
                        yield line({"type": "answer", "text": m.get("content", "").strip(),
                                    "seconds": round(time.monotonic() - t0, 1), "model": MODEL})
                        return
                    for call in calls:
                        fn = call["function"]; args = fn.get("arguments") or {}
                        if isinstance(args, str):
                            try: args = json.loads(args)
                            except ValueError: args = {}
                        yield line({"type": "step", "tool": fn["name"], "args": args, "label": _step_label(fn["name"], args)})
                        out = await s.call_tool(fn["name"], args)
                        text = "".join(getattr(c, "text", "") for c in out.content)
                        msgs.append({"role": "tool", "content": text[:6000]})
                    yield line({"type": "status", "text": "Reading results…"})
            yield line({"type": "answer", "text": "I couldn't finish that lookup. Try asking more specifically, or ask your instructor.",
                        "seconds": round(time.monotonic() - t0, 1), "model": MODEL})
    except httpx.HTTPError as e:
        yield line({"type": "error", "text": f"The local model isn't answering ({type(e).__name__}). Check that Ollama is running."})
    except Exception as e:
        yield line({"type": "error", "text": f"Helper error: {type(e).__name__}: {e}"})


@app.post("/helper/chat")
async def chat(body: ChatIn):
    return StreamingResponse(chat_events(body), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- reverse proxy to Bay Log
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
async def proxy(path: str, request: Request):
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP}
    up = await proxy_client.request(request.method, "/" + path, params=request.query_params,
                                    headers=headers, content=await request.body())
    content = up.content
    if up.headers.get("content-type", "").startswith("text/html") and b"</body>" in content and PANEL_TAG not in content:
        content = content.replace(b"</body>", PANEL_TAG + b"\n</body>", 1)
    out = Response(content=content, status_code=up.status_code,
                   headers={k: v for k, v in up.headers.items() if k.lower() not in HOP and k.lower() != "set-cookie"})
    for c in up.headers.get_list("set-cookie"):
        out.headers.append("set-cookie", c)
    return out
