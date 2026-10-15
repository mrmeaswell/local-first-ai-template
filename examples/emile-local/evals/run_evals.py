"""Emile, local: checks. Run on the box, with the app running.

  python -u evals/run_evals.py           # gate + emile + answer suites
  python -u evals/run_evals.py --local   # also one end-to-end answer on the on-prem model (slow on CPU)

Env: EMILE_DIR, EMILE_PYTHON, APP_URL (http://127.0.0.1:8091)

Suites:
  gate    the data boundary stops student data; the outbound checks catch what they should (no model)
  emile   Emile's MCP server starts and serves its tools (no model)
  answer  end to end through the app: every deliverable passes every check; student data is blocked
          before any model is called
"""
import asyncio, json, os, sys
from pathlib import Path

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import gate  # noqa: E402

APP = os.environ.get("APP_URL", "http://127.0.0.1:8091")
EMILE_PY = os.environ.get("EMILE_PYTHON", sys.executable)
results = []


def report(suite, tid, status, desc):
    results.append(status); print(f"{status:7} {suite:6} {tid:4} {desc}", flush=True)


INBOUND = [  # id, text, should block
    ("g1", "Jordan Lee (jlee42@student.rtc.edu) got 58% on the midterm.", True),
    ("g2", "Student ID 201234567 needs an extension.", True),
    ("g3", "Doe, Jane, 87\nRoe, Rick, 91", True),
    ("g4", "student Maria Lopez keeps missing labs", True),
    ("g5", "Write a CNT 290 lab for week 3 on 220-1202 2.1, 16 GB RAM, port 8006.", False),
    ("g6", "A learner coming from retail is stuck on subnetting. How do I bridge it?", False),
]
GOOD = "## Hook\nYou've sorted deliveries by urgency.\n## Core\n**LVM-thin** allocates on write; **ZFS** checksums blocks.\n## Landing\nWhich fits the POS database?"
OUTBOUND = [  # id, draft, expected failing checks
    ("o1", GOOD, set()),
    ("o2", GOOD.replace("You've", "Obviously you've"), {"shame-free"}),
    ("o3", GOOD + "\nThis lifts our pass rate.", {"no pass-rate framing"}),
    ("o4", "## Core\n" + " ".join(f"**term{i}**" for i in range(7)), {"cognitive load"}),
    ("o5", '```json\n{"questions":[{"type":"multiple_choice","level":"recall","objective":"","stem":"Pick one","options":["a","b","None of the above"],"answer":[0]}]}\n```', {"quiz spec (1 sample items)"}),
    ("o6", GOOD + "\nEmail jlee42@student.rtc.edu with this.", {"no student data"}),
    ("o7", '"Simply" tells a stuck learner they are the problem. Which word would you use instead?', set()),
    ("o8", 'As the saying goes, "it is simply done." Try it.', {"shame-free"}),
]


def gate_suite():
    for gid, text, block in INBOUND:
        got = bool(gate.student_data(text))
        report("gate", gid, "PASS" if got == block else "FAIL", f"{'blocks' if block else 'allows'}: {text[:60]!r} -> {gate.student_data(text) or 'ok'}")
    for oid, draft, expect in OUTBOUND:
        got = {c["name"] for c in gate.failures(gate.check(draft, "Review: \"Simply open the BIOS.\""))}
        report("gate", oid, "PASS" if got == expect else "FAIL", f"expect fail {sorted(expect) or 'none'}, got {sorted(got) or 'none'}")


async def emile_suite():
    p = StdioServerParameters(command=EMILE_PY, args=[str(gate.EMILE_DIR / "server.py")])
    try:
        async with stdio_client(p, errlog=open(os.devnull, "w")) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            names = {t.name for t in (await s.list_tools()).tools}
            want = {"emile_get_course_context", "emile_get_scenario", "emile_get_quiz_spec", "emile_lint_language", "emile_validate_quiz", "emile_check_load"}
            report("emile", "m1", "PASS" if want <= names else "FAIL", f"Emile server tools: {sorted(names)}")
            o = await s.call_tool("emile_get_course_context", {"code": "CNT 290"})
            report("emile", "m2", "PASS" if "Proxmox" in "".join(c.text for c in o.content) else "FAIL", "course context for CNT 290")
    except Exception as e:
        report("emile", "m1", "FAIL", f"Emile server didn't start ({type(e).__name__}: {e}); check EMILE_DIR / EMILE_PYTHON")


def chat(message, course=None, local_only=False):
    r = httpx.post(f"{APP}/api/chat", timeout=1200, json={"message": message, "course": course, "local_only": local_only})
    return [json.loads(l) for l in r.text.splitlines() if l.strip()]


QUESTIONS = [  # id, course, message, test(answer_text, events)
    ("e1", "CNT 290", "Write a module intro for CNT 290 on choosing Proxmox storage (LVM-thin vs ZFS vs directory). "
     "Learners are adult career changers, week 3, after virtual networking. Objective: choose a storage type for a workload and justify it.",
     lambda t, ev: "##" in t and gate.new_terms(t)),
    ("e2", "CNT 160", "Draft 4 sample quiz items for CNT 160 on the malware removal process: one multiple choice, one multiple answer, "
     "one true/false, one fill-in-the-blank. Map each to a 220-1202 objective and set a level for each. Use the MSCB scenario.",
     lambda t, ev: any(c["name"].startswith("quiz spec") for c in next(e for e in ev if e["type"] == "checks")["checks"])),
    ("e3", None, "Review this lab intro and push back where it drifts:\n\n\"Simply open the BIOS and disable Secure Boot. This is basic stuff, "
     "so obviously everyone should finish in 10 minutes.\"", lambda t, ev: "secure boot" in t.lower()),
]


def answer_suite(local):
    try:
        h = httpx.get(f"{APP}/api/health", timeout=15).json()
    except Exception as e:
        report("answer", "e0", "SKIPPED", f"app unreachable at {APP} ({type(e).__name__})"); return
    print(f"        Emile is using: {h.get('claude_model') if h.get('claude') == 'ok' else h.get('model') + ' (on-prem)'}", flush=True)
    ev = chat("Jordan Lee (jlee42@student.rtc.edu, ID 201234567) got 58% on the midterm. Help me write feedback.")
    report("answer", "b1", "PASS" if ev and ev[0]["type"] == "blocked" and len(ev) == 1 else "FAIL",
           "student data is stopped before any model is called: " + (ev[0].get("text", "")[:70] if ev else "no response"))
    qs = QUESTIONS + ([("l1", "CNT 290", QUESTIONS[0][2], QUESTIONS[0][3])] if local else [])
    for qid, course, msg, extra in qs:
        ev = chat(msg, course, local_only=qid.startswith("l"))
        ans = next((e for e in ev if e["type"] in ("answer", "error")), {})
        chk = next((e for e in ev if e["type"] == "checks"), {"checks": [], "revised": False})
        text = ans.get("text", "")
        failed = [f"{c['name']} ({c['detail']})" for c in chk["checks"] if not c["pass"]]
        good = ans.get("type") == "answer" and chk["checks"] and not failed and extra(text, ev)
        steps = [e["label"] for e in ev if e["type"] == "step"]
        report("answer", qid, "PASS" if good else "FAIL",
               f"{ans.get('model', '?')}{' (backup)' if ans.get('fallback') else ''} {ans.get('seconds', '?')}s steps={steps}"
               f"{' revised' if chk['revised'] else ''}{' FAILED: ' + '; '.join(failed) if failed else ''}")
        print("        " + text[:300].replace("\n", " ") + ("…" if len(text) > 300 else ""), flush=True)


gate_suite()
asyncio.run(emile_suite())
answer_suite("--local" in sys.argv)
n = {s: results.count(s) for s in ("PASS", "FAIL", "SKIPPED")}
print(f"\n{n['PASS']} passed, {n['FAIL']} failed, {n['SKIPPED']} skipped"); sys.exit(1 if n["FAIL"] else 0)
