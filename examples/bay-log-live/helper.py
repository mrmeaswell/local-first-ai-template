"""Shop Coach service: puts a read-only AI coach inside Bay Log without changing Bay Log.

One port, one hostname:
  /helper/*  -> this service (chat, health, panel assets)
  anything else -> reverse-proxied to Bay Log, with the panel <script> injected into its page

Emile's architecture: judgment in the prompt (prompts/shop-coach.md), rules in code (checks.py).
  1. The model drafts an answer, calling read-only baylog-mcp tools for every fact.
  2. checks.py tests the draft against what the tools returned (grounded, cites procedure,
     shame-free, ends with one question, concise, read-only honest).
  3. If a check fails, the model gets one revision round. The student sees the answer plus the checks.

Model: Claude (Anthropic API) when ANTHROPIC_API_KEY is set; if the API fails mid-answer the
local model (Ollama) takes over automatically. Without a key, local model only.
Progress streams back as NDJSON lines: status | step | checks | answer | error.

Env: BAYLOG_API (http://127.0.0.1:8080), OLLAMA_URL (http://127.0.0.1:11434), MODEL (qwen2.5:7b),
     HELPER_NUM_CTX (4096), ANTHROPIC_API_KEY, CLAUDE_MODEL (claude-sonnet-5),
     ANTHROPIC_URL (https://api.anthropic.com), CLAUDE_TIMEOUT (45)
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

from checks import check_answer, failures, repair_instruction

HERE = Path(__file__).resolve().parent
BAYLOG = os.environ.get("BAYLOG_API", "http://127.0.0.1:8080").rstrip("/")
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.environ.get("MODEL", "qwen2.5:7b")
NUM_CTX = int(os.environ.get("HELPER_NUM_CTX", "4096"))
SYSTEM = (HERE / "prompts" / "shop-coach.md").read_text()
MAX_ROUNDS = 5
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
ANTHROPIC = os.environ.get("ANTHROPIC_URL", "https://api.anthropic.com").rstrip("/")
CLAUDE_TIMEOUT = float(os.environ.get("CLAUDE_TIMEOUT", "45"))
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


app = FastAPI(title="Shop Coach", lifespan=lifespan)


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
    out = {"provider": "claude" if API_KEY else "local", "claude_model": CLAUDE_MODEL if API_KEY else None,
           "claude": "not configured", "model": MODEL, "baylog": "down", "ollama": "down", "model_loaded": False}
    async with httpx.AsyncClient(timeout=5) as c:
        try:
            out["baylog"] = (await c.get(f"{BAYLOG}/api/health")).json().get("status", "?")
        except Exception:
            pass
        if API_KEY:  # free metadata call: proves the key works and the model name exists
            try:
                r = await c.get(f"{ANTHROPIC}/v1/models/{CLAUDE_MODEL}", headers=_claude_headers())
                out["claude"] = "ok" if r.status_code == 200 else {401: "key rejected", 404: f"model {CLAUDE_MODEL} not found"}.get(r.status_code, f"HTTP {r.status_code}")
            except Exception as e:
                out["claude"] = f"unreachable ({type(e).__name__})"
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


def _claude_headers():
    return {"x-api-key": API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}


class Turn_:  # shared state for one chat turn
    def __init__(self):
        self.evidence: list[str] = []
        self.answer = ""
        self.model = ""
        self.revise = None  # async fn(instruction) -> revised text


def _line(obj):
    return (json.dumps(obj) + "\n").encode()


async def _run_tool(s, st, name, args):
    out = await s.call_tool(name, args)
    text = "".join(getattr(c, "text", "") for c in out.content)[:6000]
    st.evidence.append(text)
    return text


async def run_claude(s, mcp_tools, system, history, message, st):
    """Claude tool-use loop. Raises on any API problem so the caller can fall back."""
    tools = [{"name": t.name, "description": t.description or "", "input_schema": t.inputSchema} for t in mcp_tools]
    msgs = [t for t in history] + [{"role": "user", "content": message}]
    # each call opens its own client, so revise() still works after this loop has returned
    async def call(extra=None):
        async with httpx.AsyncClient(timeout=CLAUDE_TIMEOUT) as c:
            r = await c.post(f"{ANTHROPIC}/v1/messages", headers=_claude_headers(), json={
                "model": CLAUDE_MODEL, "max_tokens": 700, "system": system, "tools": tools, "messages": msgs, **(extra or {})})
        if r.status_code != 200:
            raise httpx.HTTPStatusError(f"Claude API {r.status_code}: {r.text[:200]}", request=r.request, response=r)
        return r.json()
    for _ in range(MAX_ROUNDS):
        res = await call()
        msgs.append({"role": "assistant", "content": res["content"]})
        uses = [b for b in res["content"] if b.get("type") == "tool_use"]
        if res.get("stop_reason") != "tool_use" or not uses:
            st.answer = "".join(b.get("text", "") for b in res["content"] if b.get("type") == "text").strip()
            st.model = CLAUDE_MODEL

            async def revise(instruction):
                msgs.append({"role": "user", "content": instruction})
                r2 = await call({"tool_choice": {"type": "none"}})
                return "".join(b.get("text", "") for b in r2["content"] if b.get("type") == "text").strip()
            st.revise = revise
            return
        results = []
        for b in uses:
            args = b.get("input") or {}
            yield {"type": "step", "tool": b["name"], "args": args, "label": _step_label(b["name"], args)}
            results.append({"type": "tool_result", "tool_use_id": b["id"], "content": await _run_tool(s, st, b["name"], args)})
        msgs.append({"role": "user", "content": results})
        yield {"type": "status", "text": "Reading results…"}


async def run_local(s, mcp_tools, system, history, message, st):
    """Ollama tool loop (on-prem)."""
    tools = [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.inputSchema}}
             for t in mcp_tools]
    msgs = [{"role": "system", "content": system}] + list(history) + [{"role": "user", "content": message}]
    # each call opens its own client, so revise() still works after this loop has returned
    async def call(with_tools=True):
        async with httpx.AsyncClient(timeout=600) as c:
            r = await c.post(f"{OLLAMA}/api/chat", json={
                "model": MODEL, "messages": msgs, "stream": False, "keep_alive": "60m",
                **({"tools": tools} if with_tools else {}), "options": {"temperature": 0.2, "num_ctx": NUM_CTX}})
        r.raise_for_status()
        return r.json()["message"]
    for _ in range(MAX_ROUNDS):
        m = await call()
        msgs.append(m)
        calls = m.get("tool_calls") or []
        if not calls:
            st.answer, st.model = (m.get("content") or "").strip(), MODEL

            async def revise(instruction):
                msgs.append({"role": "user", "content": instruction})
                return ((await call(with_tools=False)).get("content") or "").strip()
            st.revise = revise
            return
        for call_ in calls:
            fn = call_["function"]; args = fn.get("arguments") or {}
            if isinstance(args, str):
                try: args = json.loads(args)
                except ValueError: args = {}
            yield {"type": "step", "tool": fn["name"], "args": args, "label": _step_label(fn["name"], args)}
            msgs.append({"role": "tool", "content": await _run_tool(s, st, fn["name"], args)})
        yield {"type": "status", "text": "Reading results…"}


async def chat_events(body: ChatIn):
    t0 = time.monotonic()
    system = SYSTEM + (f"\n\nOpen ticket on the student's screen: {body.ticket_id}" if body.ticket_id else
                       "\n\nNo ticket is open on the student's screen.")
    history = [t.model_dump() for t in body.history[-8:]]
    context = f"{body.message} {body.ticket_id or ''}"
    params = StdioServerParameters(command=sys.executable, args=[str(HERE / "baylog_mcp.py")],
                                   env={**os.environ, "BAYLOG_API": BAYLOG})
    st, fallback = Turn_(), None
    try:
        async with stdio_client(params, errlog=open(os.devnull, "w")) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            mcp_tools = (await s.list_tools()).tools
            yield _line({"type": "status", "text": "Thinking…"})
            if API_KEY:
                try:
                    async for ev in run_claude(s, mcp_tools, system, history, body.message, st):
                        yield _line(ev)
                except (httpx.HTTPError, KeyError, ValueError) as e:
                    fallback = str(e)[:160] or type(e).__name__
                    print(f"[helper] Claude failed, falling back to {MODEL}: {fallback}", file=sys.stderr)
                    st = Turn_()
                    yield _line({"type": "status", "text": "Cloud model unreachable. Switching to the on-prem model…"})
            if not st.revise:
                async for ev in run_local(s, mcp_tools, system, history, body.message, st):
                    yield _line(ev)
            if not st.revise:
                yield _line({"type": "answer", "text": "I couldn't finish that lookup. Try asking more specifically, or ask your instructor.",
                             "seconds": round(time.monotonic() - t0, 1), "model": st.model or MODEL, "fallback": bool(fallback)})
                return

            # Rules in code: check the draft against the evidence; one revision round if anything fails.
            evidence = "\n".join(st.evidence)
            yield _line({"type": "status", "text": "Checking the answer…"})
            checks, revised = check_answer(st.answer, evidence, context), False
            if failures(checks):
                yield _line({"type": "status", "text": "Revising: " + ", ".join(c["name"] for c in failures(checks)) + "…"})
                try:
                    second = await st.revise(repair_instruction(checks))
                    checks2 = check_answer(second, evidence, context)
                    if second and len(failures(checks2)) <= len(failures(checks)):
                        st.answer, checks, revised = second, checks2, True
                except Exception as e:  # keep the first draft; its checks are shown honestly
                    print(f"[helper] revision failed: {type(e).__name__}: {e}", file=sys.stderr)
            yield _line({"type": "checks", "checks": checks, "revised": revised})
            yield _line({"type": "answer", "text": st.answer or "(no answer)", "seconds": round(time.monotonic() - t0, 1),
                         "model": st.model, "fallback": bool(fallback)})
    except httpx.HTTPError as e:
        yield _line({"type": "error", "text": f"No model is answering ({type(e).__name__}). Check Ollama and the network."})
    except Exception as e:
        yield _line({"type": "error", "text": f"Helper error: {type(e).__name__}: {e}"})


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
