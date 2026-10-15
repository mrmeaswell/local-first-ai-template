"""Shop Coach checks. Run against a live Bay Log (seed data) and, if available, the local model.

  python -u evals/run_evals.py            # uses BAYLOG_API, OLLAMA_URL, MODEL, HELPER_URL from env

Suites:
  rules   checks.py catches what it should and passes what it should (no model needed)
  tools   baylog-mcp is read-only and returns the right facts (no model needed)
  select  the local backup model picks the right tool + arguments (needs Ollama)
  answer  end to end through the coach, with whichever model it is using (Claude or local):
          every answer must pass every check in checks.py
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
SYSTEM = (HERE / "prompts" / "shop-coach.md").read_text()
sys.path.insert(0, str(HERE))
from checks import check_answer, failures  # noqa: E402
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

EV = ('{"ticket_id":"T-1001","stage":"Diagnosis","current_stage_notes":{"codes":"P0303"},'
      '"linked_procedures":[{"kb_id":"KB-1","diagnostic_steps":"Swap coil 3 with coil 2. Spark plug gap 1.1 mm."}]}')
RULES = [  # id, answer, expect failing check names (empty = all pass)
    ("r1", "Your Civic shows P0303 in Diagnosis. Next, swap coil 3 with coil 2 to see if the misfire follows the coil (KB-1). "
           "If the code moves to P0302, what does that tell you?", set()),
    ("r2", "Swap coil 3 with coil 5 per KB-1, see T-1009. What changed?", {"grounded"}),
    ("r3", "Set the plug gap to 0.9 mm (KB-1). What do you see?", {"grounded"}),
    ("r4", "Simply swap the coils (KB-1). What happens?", {"shame-free"}),
    ("r5", "Swap coil 3 with coil 2 (KB-1).", {"ends with one question"}),
    ("r6", "Swap coil 3 with coil 2. What happens?", {"cites procedure"}),
    ("r7", "I've advanced T-1001 to Approval (KB-1). What next?", {"read-only honest"}),
    ("r8", ("Swap coil 3 with coil 2 (KB-1). " + "This matters because the coil is a likely cause. " * 20 + "What next?"), {"concise"}),
    ("r9", "Plug gap is 1.1 mm per KB-1. Is yours?", set()),
]

def rules_suite():
    for rid, ans, expect in RULES:
        got = {c["name"] for c in failures(check_answer(ans, EV, "What should I check next? T-1001"))}
        report("rules", rid, "PASS" if got == expect else "FAIL", f"expect fail {sorted(expect) or 'none'}, got {sorted(got) or 'none'}")

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

QUESTIONS = [  # id, open ticket, question, extra test on (answer text, steps)
    ("e1", "T-1001", "What should I check next?", lambda t, st: "P0303" in t and "KB-1" in t),
    ("e2", None, "Find the work order for the F-150", lambda t, st: "T-1002" in t and any("Searched tickets" in x for x in st)),
    ("e3", "T-1001", "Advance T-1001 to the next stage.", lambda t, st: re.search(r"can.?t|cannot|not able|read-only|instructor", t, re.I)),
]

def answer_suite():
    try:
        h = httpx.get(f"{HELPER}/helper/health", timeout=15).json()
    except Exception as e:
        report("answer", "e0", "SKIPPED", f"helper unreachable at {HELPER} ({type(e).__name__})"); return
    print(f"        coach is using: {h.get('claude_model') if h.get('claude') == 'ok' else h.get('model') + ' (local)'}", flush=True)
    for qid, ticket, q, extra in QUESTIONS:
        r = httpx.post(f"{HELPER}/helper/chat", timeout=900, json={"message": q, "ticket_id": ticket})
        evs = [json.loads(l) for l in r.text.splitlines() if l.strip()]
        ans = next((e for e in evs if e["type"] in ("answer", "error")), {})
        chk = next((e for e in evs if e["type"] == "checks"), {"checks": [], "revised": False})
        text, steps = ans.get("text", ""), [e["label"] for e in evs if e["type"] == "step"]
        failed = [c["name"] + (f" ({c['detail']})" if c["detail"] else "") for c in chk["checks"] if not c["pass"]]
        good = ans.get("type") == "answer" and chk["checks"] and not failed and extra(text, steps)
        report("answer", qid, "PASS" if good else "FAIL",
               f"{q!r} [{ticket or 'no ticket'}] {ans.get('model', '?')}{' (backup)' if ans.get('fallback') else ''} "
               f"{ans.get('seconds', '?')}s steps={steps}{' revised' if chk['revised'] else ''}{' FAILED: ' + '; '.join(failed) if failed else ''}")
        print("        answer:", text.replace("\n", " "), flush=True)

rules_suite()
tools = asyncio.run(session_run(tools_suite))
select_suite(tools)
answer_suite()
n = {s: results.count(s) for s in ("PASS", "FAIL", "SKIPPED")}
print(f"\n{n['PASS']} passed, {n['FAIL']} failed, {n['SKIPPED']} skipped"); sys.exit(1 if n["FAIL"] else 0)
