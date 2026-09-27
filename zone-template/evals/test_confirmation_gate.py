"""Checks the human-in-the-loop gate: write tools expose no self-approval parameter,
and assistant.py refuses a write when the human says no."""
import builtins, importlib.util, pathlib, re, sys
ROOT = pathlib.Path(__file__).parent.parent; fails = 0
src = (ROOT / "mcp/zone-mcp/server.py").read_text()
ok = "confirmed" not in re.sub(r'""".*?"""', "", src, flags=re.S)
print("PASS" if ok else "FAIL", "gate g1 - write tools have no model-settable confirmation flag"); fails += not ok
spec = importlib.util.spec_from_file_location("assistant", ROOT / "assistant.py"); a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
for answer, want in [("n", False), ("", False), ("y", True)]:
    builtins.input = lambda *_: answer; got = a.human_approves("advance_stage", {"record_id": 2})
    ok = got == want; print("PASS" if ok else "FAIL", f"gate g2 - answer {answer!r} -> approved={got}"); fails += not ok
sys.exit(1 if fails else 0)
