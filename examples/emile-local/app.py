"""Emile, local: the Emile curriculum collaborator as a standalone instructor web app.

Emile's public repo is "a music library plus a tuner": the prompt, the specs, and validators.
This app adds the musician and the stage:

  Browser ──► app.py ──► inbound gate (gate.student_data): student data never reaches any model
                     ──► model: Claude (API) ─┐ on any API failure ─► Ollama (on-prem)
                     │        ⇄ Emile MCP server (stdio): course context, MSCB, quiz spec, validators
                     ──► outbound gate (gate.check, Emile's own validators.py) ─► one revision if needed
                     ──► the instructor sees the deliverable plus every check

Env: EMILE_DIR (./emile), EMILE_PYTHON (python for Emile's server; default: this python),
     ANTHROPIC_API_KEY, CLAUDE_MODEL (claude-sonnet-5), ANTHROPIC_URL, CLAUDE_TIMEOUT (120),
     OLLAMA_URL (http://127.0.0.1:11434), MODEL (qwen2.5:7b), EMILE_NUM_CTX (8192)
Run: uvicorn app:app --host 0.0.0.0 --port 8091
"""
import asyncio
import json
import os
import re
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, Field

import gate

HERE = Path(__file__).resolve().parent
EMILE_DIR = gate.EMILE_DIR
EMILE_PY = os.environ.get("EMILE_PYTHON", sys.executable)
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
ANTHROPIC = os.environ.get("ANTHROPIC_URL", "https://api.anthropic.com").rstrip("/")
CLAUDE_TIMEOUT = float(os.environ.get("CLAUDE_TIMEOUT", "120"))
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.environ.get("MODEL", "qwen2.5:7b")
NUM_CTX = int(os.environ.get("EMILE_NUM_CTX", "8192"))
MAX_ROUNDS = 6
CLAUDE_LAST = {"ok": None, "error": ""}  # result of the last real Claude call; the free health check can't see billing errors
ADDENDUM = (HERE / "prompts" / "app-addendum.md").read_text()
# Add-on modes: Markdown files dropped into EMILE_ADDENDA on the server (kept out of this repo, so an
# add-on can have its own owner). Header lines before a "---" line configure the mode; the rest is prompt.
ADDENDA = Path(os.environ.get("EMILE_ADDENDA", HERE / "addenda"))


def data(name: str) -> str:
    return (EMILE_DIR / "data" / name).read_text(encoding="utf-8")


def courses() -> list[dict]:
    out = []
    for p in sorted((EMILE_DIR / "data").glob("course-*.md")):
        m = re.search(r"\|\s*Title\s*\|\s*(.+?)\s*\|", p.read_text(encoding="utf-8"))
        code = p.stem.removeprefix("course-").upper()
        out.append({"code": re.sub(r"^([A-Z]+)(\d+)$", r"\1 \2", code), "title": m.group(1) if m else ""})
    return out


async def warm_local():
    try:
        async with httpx.AsyncClient(timeout=600) as c:
            await c.post(f"{OLLAMA}/api/generate", json={"model": MODEL, "prompt": "ok", "stream": False,
                                                         "keep_alive": "60m", "options": {"num_predict": 1}})
    except Exception as e:
        print(f"[emile] local warm-up skipped: {e}", file=sys.stderr)


@asynccontextmanager
async def lifespan(_app):
    task = asyncio.create_task(warm_local())
    yield
    task.cancel()


app = FastAPI(title="Emile, local", lifespan=lifespan)


class Turn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=20000)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    course: str | None = Field(default=None, max_length=12)
    mode: str | None = Field(default=None, max_length=40)
    local_only: bool = False
    history: list[Turn] = Field(default_factory=list, max_length=16)


@app.get("/")
async def index():
    return FileResponse(HERE / "static" / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/api/courses")
async def api_courses():
    return courses()


def modes() -> dict:
    """{id: {name, required, starters, text}} from ADDENDA/*.md (README.md ignored).

    # Name                                   first heading = the mode's display name
    Required headings: A | B | C             sections every deliverable in this mode must have (checked in code)
    Starter: Title | short description | prompt text (use \\n for new lines, [brackets] for blanks)
    ---
    prompt text appended to Emile's system prompt
    """
    out = {}
    if not ADDENDA.is_dir():
        return out
    for f in sorted(ADDENDA.glob("*.md")):
        if f.name.lower() == "readme.md":
            continue
        raw = f.read_text(encoding="utf-8")
        head, sep, body = raw.partition("\n---\n")
        if not sep:
            head, body = "", raw
        name = next((l[2:].strip() for l in raw.splitlines() if l.startswith("# ")), f.stem)
        req, starters = [], []
        for l in head.splitlines():
            k, _, v = l.partition(":")
            if k.strip().lower() == "required headings":
                req = [x.strip() for x in v.split("|") if x.strip()]
            elif k.strip().lower() == "starter":
                parts = [x.strip() for x in v.split("|", 2)]
                if len(parts) == 3:
                    starters.append({"t": parts[0], "d": parts[1], "q": parts[2].replace("\\n", "\n")})
        out[f.stem] = {"name": name, "required": req, "starters": starters, "text": body.strip()}
    return out


@app.get("/api/modes")
async def api_modes():
    return [{"id": k, "name": v["name"], "starters": v["starters"], "required": v["required"]} for k, v in modes().items()]


def _claude_headers():
    return {"x-api-key": API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}


@app.get("/api/health")
async def health():
    out = {"emile": "ok" if (EMILE_DIR / "data" / "emile-system.md").is_file() else f"not found at {EMILE_DIR}",
           "claude_model": CLAUDE_MODEL if API_KEY else None, "claude": "not configured",
           "model": MODEL, "ollama": "down", "model_loaded": False}
    async with httpx.AsyncClient(timeout=5) as c:
        if API_KEY:
            try:
                r = await c.get(f"{ANTHROPIC}/v1/models/{CLAUDE_MODEL}", headers=_claude_headers())
                out["claude"] = "ok" if r.status_code == 200 else {401: "key rejected", 404: f"model {CLAUDE_MODEL} not found"}.get(r.status_code, f"HTTP {r.status_code}")
                if out["claude"] == "ok" and CLAUDE_LAST["ok"] is False:
                    out["claude"] = CLAUDE_LAST["error"]
            except Exception as e:
                out["claude"] = f"unreachable ({type(e).__name__})"
        try:
            names = (MODEL, MODEL + ":latest")
            tags = (await c.get(f"{OLLAMA}/api/tags")).json().get("models", [])
            out["ollama"] = "ok" if any(m["name"] in names for m in tags) else f"model {MODEL} not pulled"
            out["model_loaded"] = any(m["name"] in names for m in (await c.get(f"{OLLAMA}/api/ps")).json().get("models", []))
        except Exception:
            pass
    return out


@app.get("/static/{name}")
async def asset(name: str):
    f = (HERE / "static" / name).resolve()
    if f.parent != (HERE / "static").resolve() or not f.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(f, headers={"Cache-Control": "no-cache"})


# ---------------------------------------------------------------- the model loop
LABELS = {"emile_get_course_context": lambda a: f"Read course context: {a.get('code', '?')}",
          "emile_get_scenario": lambda a: "Read the MSCB story bible",
          "emile_get_quiz_spec": lambda a: "Read the quiz package spec",
          "emile_get_antipatterns": lambda a: "Read the anti-patterns",
          "emile_lint_language": lambda a: "Ran the language lint",
          "emile_validate_quiz": lambda a: "Validated a quiz draft",
          "emile_check_load": lambda a: "Checked cognitive load"}


def label(name, args):
    return LABELS.get(name, lambda a: name)(args or {})


def line(obj):
    return (json.dumps(obj) + "\n").encode()


class State:
    def __init__(self):
        self.answer, self.model, self.revise = "", "", None


async def tool_text(s, name, args):
    out = await s.call_tool(name, args)
    text = "".join(getattr(c, "text", "") for c in out.content)
    return text[:12000]


async def run_claude(s, tools_, system, history, message, st):
    tools = [{"name": t.name, "description": t.description or "", "input_schema": t.inputSchema} for t in tools_]
    msgs = list(history) + [{"role": "user", "content": message}]

    async def call(extra=None):
        async with httpx.AsyncClient(timeout=CLAUDE_TIMEOUT) as c:
            r = await c.post(f"{ANTHROPIC}/v1/messages", headers=_claude_headers(), json={
                "model": CLAUDE_MODEL, "max_tokens": 6000, "system": system, "tools": tools,
                "messages": msgs, **(extra or {})})
        if r.status_code != 200:
            msg = (r.json().get("error", {}).get("message", "") if "json" in r.headers.get("content-type", "") else "") or r.text[:120]
            CLAUDE_LAST.update(ok=False, error="no API credit" if "credit balance" in msg else f"API error {r.status_code}")
            raise httpx.HTTPStatusError(f"Claude API {r.status_code}: {msg[:200]}", request=r.request, response=r)
        CLAUDE_LAST.update(ok=True, error="")
        return r.json()

    text_of = lambda res: "".join(b.get("text", "") for b in res["content"] if b.get("type") == "text").strip()
    for _ in range(MAX_ROUNDS):
        res = await call()
        msgs.append({"role": "assistant", "content": res["content"]})
        uses = [b for b in res["content"] if b.get("type") == "tool_use"]
        if res.get("stop_reason") != "tool_use" or not uses:
            st.answer, st.model = text_of(res), CLAUDE_MODEL

            async def revise(instruction):
                msgs.append({"role": "user", "content": instruction})
                return text_of(await call({"tool_choice": {"type": "none"}}))
            st.revise = revise
            return
        results = []
        for b in uses:
            args = b.get("input") or {}
            yield {"type": "step", "label": label(b["name"], args)}
            results.append({"type": "tool_result", "tool_use_id": b["id"], "content": await tool_text(s, b["name"], args)})
        msgs.append({"role": "user", "content": results})
        yield {"type": "status", "text": "Drafting…"}


async def run_local(s, tools_, system, history, message, st):
    tools = [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.inputSchema}}
             for t in tools_]
    msgs = [{"role": "system", "content": system}] + list(history) + [{"role": "user", "content": message}]

    async def call(with_tools=True):
        async with httpx.AsyncClient(timeout=900) as c:
            r = await c.post(f"{OLLAMA}/api/chat", json={
                "model": MODEL, "messages": msgs, "stream": False, "keep_alive": "60m",
                **({"tools": tools} if with_tools else {}), "options": {"temperature": 0.3, "num_ctx": NUM_CTX}})
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
        for c_ in calls:
            fn = c_["function"]; args = fn.get("arguments") or {}
            if isinstance(args, str):
                try: args = json.loads(args)
                except ValueError: args = {}
            yield {"type": "step", "label": label(fn["name"], args)}
            msgs.append({"role": "tool", "content": await tool_text(s, fn["name"], args)})
        yield {"type": "status", "text": "Drafting…"}


GENERAL_MODE = """## General mode (no course selected)
The instructor may teach any subject: nursing, welding, accounting, ESL, automotive, and so on. In this mode:
- Don't default to the MSCB scenario or its service providers, and don't cite CompTIA or AWS objectives unless the instructor does.
- Anchor examples in the instructor's own field and in their learners' working lives. If the field isn't clear from the request, ask what it is (it counts as one of your three questions).
- If the request still contains [bracketed placeholders], ask the instructor to fill them in instead of guessing.
- Quiz objectives use whatever standard the instructor names, or "Course objective N" if none. Rubrics use the instructor's scale if given; otherwise Not Yet / Approaching / Meeting / Exceeding."""


def system_prompt(course: str | None, mode: dict | None = None) -> str:
    parts = [data("emile-system.md"), ADDENDUM]
    f = EMILE_DIR / "data" / f"course-{re.sub(r'[^a-z0-9]', '', (course or '').lower())}.md"
    if course and f.is_file():
        parts.append(f.read_text(encoding="utf-8") + f"\n\nThe instructor is working on {course}.")
    else:
        parts.append(GENERAL_MODE)
    if mode:
        parts.append(f"## {mode['name']} mode\nThe instructor turned on the {mode['name']} add-on. Follow it for this deliverable; "
                     "where it conflicts with the length guidance above, it wins."
                     + (f"\nEvery deliverable must include these sections as ## headings: {', '.join(mode['required'])}." if mode["required"] else "")
                     + "\n\n" + mode["text"])
    return "\n\n".join(parts)


async def chat_events(body: ChatIn):
    t0 = time.monotonic()
    secs = lambda: round(time.monotonic() - t0, 1)

    # Inbound gate: runs before any model sees anything.
    found = gate.student_data(body.message)
    if found:
        yield line({"type": "blocked", "found": found,
                    "text": "Stopped before sending: this looks like it contains " + ", ".join(found) + ". "
                            "Emile works with instructors only (FERPA). Remove identifying details, or describe "
                            "the learner by role (\"a learner coming from retail\"), and send again. "
                            "Nothing was sent to any model."})
        return

    history = [t.model_dump() for t in body.history[-12:]]
    params = StdioServerParameters(command=EMILE_PY, args=[str(EMILE_DIR / "server.py")], env={**os.environ})
    st, fallback = State(), None
    try:
        async with stdio_client(params, errlog=open(os.devnull, "w")) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            # The model gets Emile's library (course, scenario, spec, anti-patterns), not the validators:
            # the code runs those on every answer, so the musician never tunes its own instrument.
            tools_ = [t for t in (await s.list_tools()).tools if t.name.startswith("emile_get_")]
            mode = modes().get(body.mode) if body.mode else None
            system = system_prompt(body.course, mode)
            req, mname = (mode["required"], mode["name"]) if mode else (None, "")
            yield line({"type": "status", "text": "Thinking…"})
            if API_KEY and not body.local_only:
                try:
                    async for ev in run_claude(s, tools_, system, history, body.message, st):
                        yield line(ev)
                except (httpx.HTTPError, KeyError, ValueError) as e:
                    fallback = str(e)[:160] or type(e).__name__
                    if CLAUDE_LAST["ok"] is not False:
                        CLAUDE_LAST.update(ok=False, error=f"unreachable ({type(e).__name__})")
                    print(f"[emile] Claude failed, falling back to {MODEL}: {fallback}", file=sys.stderr)
                    st = State()
                    yield line({"type": "status", "text": "Cloud model unreachable. Switching to the on-prem model…"})
            if not st.revise:
                if body.local_only or not API_KEY:
                    yield line({"type": "status", "text": "Thinking on the on-prem model…"})
                async for ev in run_local(s, tools_, system, history, body.message, st):
                    yield line(ev)
            if not st.revise:
                yield line({"type": "error", "text": "Emile couldn't finish within the tool-call limit. Try a narrower request."})
                return

            if not st.answer.strip():  # e.g. the model stopped mid tool call; ask once for the text itself
                yield line({"type": "status", "text": "Asking Emile for the written answer…"})
                try:
                    st.answer = await st.revise("Please give your full answer now as Markdown text, with no tool calls.")
                except Exception as e:
                    print(f"[emile] empty-answer retry failed: {type(e).__name__}: {e}", file=sys.stderr)
                if not st.answer.strip():
                    yield line({"type": "error", "text": "Emile didn't produce an answer that time. Try again, or narrow the request."})
                    return

            # Outbound gate: Emile's validators on the draft; one revision round if anything fails.
            yield line({"type": "status", "text": "Checking against Emile's rules…"})
            checks, revised = gate.check(st.answer, body.message, req, mname), False
            if gate.failures(checks):
                yield line({"type": "status", "text": "Revising: " + ", ".join(c["name"] for c in gate.failures(checks)) + "…"})
                try:
                    second = await st.revise(gate.repair_instruction(checks))
                    checks2 = gate.check(second, body.message, req, mname)
                    if second and len(gate.failures(checks2)) <= len(gate.failures(checks)):
                        st.answer, checks, revised = second, checks2, True
                except Exception as e:
                    print(f"[emile] revision failed: {type(e).__name__}: {e}", file=sys.stderr)
            yield line({"type": "checks", "checks": checks, "revised": revised, "terms": gate.new_terms(st.answer)})
            yield line({"type": "answer", "text": st.answer or "(no answer)", "seconds": secs(), "model": st.model, "mode": mname,
                        "fallback": bool(fallback), "local": st.model == MODEL})
    except httpx.HTTPError as e:
        yield line({"type": "error", "text": f"No model is answering ({type(e).__name__}). Check Ollama and the network."})
    except Exception as e:
        yield line({"type": "error", "text": f"Emile error: {type(e).__name__}: {e}"})


@app.post("/api/chat")
async def chat(body: ChatIn):
    return StreamingResponse(chat_events(body), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
