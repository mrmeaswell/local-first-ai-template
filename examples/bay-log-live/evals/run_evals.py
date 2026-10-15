"""Shop Helper checks. Run against a live Bay Log (seed data) and, if available, the local model.

  python -u evals/run_evals.py            # uses BAYLOG_API, OLLAMA_URL, MODEL, HELPER_URL from env

Suites:
  tools   baylog-mcp is read-only and returns the right facts (no model needed)
  select  the model picks the right tool + arguments (needs Ollama)
  answer  one end-to-end question through the helper: answer cites P0303 and KB-1 (needs helper + Ollama)
"""
import asyncio, json, os, re, sys
from pathlib import Path

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent.parent
BAYLOG = os.environ.get("BAYLOG_API", "http://127.0.0.1:8080")
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("MODEL", "qwen2.5:7b")
HELPER = os.environ.get("HELPER_URL", "http://127.0.0.1:8090")
SYSTEM = (HERE / "prompts" / "shop-helper.md").read_text()
results = []

def report(suite, tid, status, desc):
    results.append(status); print(f"{status:7} {suite:7} {tid:4} {desc}", flush=True)

async def session_run(fn):
    p = StdioServerParameters(command=sys.executable, args=[str(HERE / "baylog_mcp.py")], env={**os.environ, "BAYLOG_API": BAYLOG})
    async with stdio_client(p, errlog=open(os.devnull, "w")) as (r, w), ClientSession(r, w) as s:
        await s.initialize(); return await fn(s)

async def call(s, name, args):
    o = await s.call_tool(name, args); return json.loads("".join(c.text for c in o.content))

async def tools_suite(s):
    tools = {t.name: t for t in (await s.list_tools()).tools}
    report("tools", "k1", "PASS" if set(tools) == {"get_ticket", "search_tickets", "get_board", "search_kb"} else "FAIL",
           f"read-only tool set: {sorted(tools)}")
    t = await call(s, "get_ticket", {"ticket_id": "T-1001"})
    steps = " ".join(p.get("diagnostic_steps", "") for p in t.get("linked_procedures", []))
    report("tools", "k2", "PASS" if t.get("current_stage_notes", {}).get("codes") == "P0303" and "KB-1" in json.dumps(t) and "coil" in steps else "FAIL",
           "get_ticket T-1001 carries code P0303 and the linked KB-1 steps")
    bad = await call(s, "get_ticket", {"ticket_id": "456"})
    report("tools", "k3", "PASS" if "error" in bad else "FAIL", "a guessed non-ticket ID is refused with a pointer to search")
    f = await call(s, "search_tickets", {"query": "F150 brakes"})
    report("tools", "k4", "PASS" if f["results"] and f["results"][0]["ticket_id"] == "T-1002" else "FAIL", "search_tickets 'F150 brakes' -> T-1002")
    k = await call(s, "search_kb", {"query": "P0303 misfire"})
    report("tools", "k5", "PASS" if k["results"] and k["results"][0]["kb_id"] == "KB-1" else "FAIL", "search_kb 'P0303 misfire' -> KB-1")
    return [{"type": "function", "function": {"name": x.name, "description": x.description, "parameters": x.inputSchema}} for x in tools.values()]

CASES = [  # id, open ticket, prompt, acceptable (tool, check-args) pairs
    ("s1", "T-1001", "What should I check next?", [("get_ticket", lambda a: a.get("ticket_id", "").upper() == "T-1001")]),
    ("s2", None, "Find the work order for the Ford F-150.", [("search_tickets", lambda a: re.search(r"f-?150|ford", a.get("query", ""), re.I))]),
    ("s3", None, "Which jobs are waiting on QC?", [("get_board", lambda a: True), ("search_tickets", lambda a: "qc" in a.get("query", "").lower())]),
    ("s4", None, "How do I diagnose a car that won't crank?", [("search_kb", lambda a: "crank" in a.get("query", "").lower())]),
    ("s5", None, "What's blocking T-1002 from moving on?", [("get_ticket", lambda a: a.get("ticket_id", "").upper() == "T-1002")]),
]

def select_suite(tools):
    try:
        names = [m["name"] for m in httpx.get(f"{OLLAMA}/api/tags", timeout=15).json().get("models", [])]
        ok = any(n in (MODEL, MODEL + ":latest") for n in names)
        why = "" if ok else f"model {MODEL} not pulled; available: {', '.join(names) or 'none'}"
    except Exception as e:
        ok, why = False, f"Ollama unreachable at {OLLAMA} ({type(e).__name__})"
    for cid, ticket, prompt, accept in CASES:
        if not ok: report("select", cid, "SKIPPED", why); continue
        sysmsg = SYSTEM + (f"\n\nOpen ticket on the student's screen: {ticket}" if ticket else "\n\nNo ticket is open on the student's screen.")
        m = httpx.post(f"{OLLAMA}/api/chat", timeout=600, json={"model": MODEL, "stream": False, "tools": tools,
            "options": {"temperature": 0, "num_ctx": 4096},
            "messages": [{"role": "system", "content": sysmsg}, {"role": "user", "content": prompt}]}).json()["message"]
        c = (m.get("tool_calls") or [{}])[0].get("function", {}); args = c.get("arguments") or {}
        good = any(c.get("name") == name and chk(args) for name, chk in accept)
        report("select", cid, "PASS" if good else "FAIL", f"{prompt!r} [{ticket or 'no ticket'}] -> {c.get('name')}({args})")
    return ok

def answer_suite():
    try:
        r = httpx.post(f"{HELPER}/helper/chat", timeout=900, json={"message": "What should I check next?", "ticket_id": "T-1001"})
    except Exception as e:
        report("answer", "e1", "SKIPPED", f"helper unreachable at {HELPER} ({type(e).__name__})"); return
    evs = [json.loads(l) for l in r.text.splitlines() if l.strip()]
    ans = next((e for e in evs if e["type"] in ("answer", "error")), {})
    text = ans.get("text", "")
    good = ans.get("type") == "answer" and "P0303" in text and "KB-1" in text and "?" in text
    report("answer", "e1", "PASS" if good else "FAIL",
           f"T-1001 'What should I check next?' in {ans.get('seconds', '?')}s, steps={[e['label'] for e in evs if e['type'] == 'step']}")
    print("        answer:", text.replace("\n", " "), flush=True)

tools = asyncio.run(session_run(tools_suite))
if select_suite(tools):
    answer_suite()
n = {s: results.count(s) for s in ("PASS", "FAIL", "SKIPPED")}
print(f"\n{n['PASS']} passed, {n['FAIL']} failed, {n['SKIPPED']} skipped"); sys.exit(1 if n["FAIL"] else 0)
