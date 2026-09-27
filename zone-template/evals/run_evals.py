"""Deterministic eval runner (Section 13). Negative suite must be 100%.

Each run starts its OWN API on a throwaway, freshly seeded database, so evals never touch
real data and results don't depend on earlier runs.
Scope: these evals test the API's rules only. They do NOT yet test the model's tool
selection (the Section 13 promotion gate). That is a Phase 1 student deliverable."""
import json, pathlib, subprocess, sys, tempfile, time, httpx
D = pathlib.Path(__file__).parent; ROOT = D.parent; PORT = 8099; API = f"http://127.0.0.1:{PORT}"
SEED = ROOT.parent / "examples/bay-log/seed.sql"
TOKENS = {"student": "student-demo-token", "lead": "lead-demo-token"}

def call(c, role="lead", body=None, headers=None):
    h = headers if headers is not None else ({"Authorization": f"Bearer {TOKENS[role]}"} if role in TOKENS else {})
    kw = {"content": body} if isinstance(body, str) else {"json": body}
    return httpx.request(c[0], API + c[1], headers=h, **kw)

tmp = tempfile.mkdtemp(); db = pathlib.Path(tmp) / "eval.db"
srv = subprocess.Popen([sys.executable, str(ROOT / "api/app.py"), "--db", str(db), "--seed", str(SEED), "--port", str(PORT)], stdout=subprocess.DEVNULL)
fails = 0
try:
    for _ in range(50):
        try: httpx.get(API + "/zone"); break
        except httpx.TransportError: time.sleep(0.1)
    for line in (D / "golden.jsonl").read_text().splitlines():
        t = json.loads(line); r = call(t["call"]).json(); ok = True
        if "expect" in t: ok = all(r.get(k) == v for k, v in t["expect"].items())
        if "expect_contains_id" in t: ok = any(x["id"] == t["expect_contains_id"] for x in r)
        if "expect_min_len" in t: ok = len(r) >= t["expect_min_len"]
        print(("PASS" if ok else "FAIL"), "golden", t["id"]); fails += not ok
    for line in (D / "negative.jsonl").read_text().splitlines():
        t = json.loads(line)
        r = call(t["call"], t.get("role"), t.get("body"), t.get("headers"))
        ok = r.status_code == t["expect_status"]
        if ok and "then" in t:  # verify the rejected request changed nothing
            ok = all(call(t["then"]["call"]).json().get(k) == v for k, v in t["then"]["expect"].items())
        print(("PASS" if ok else "FAIL"), "negative", t["id"], "-", t["desc"]); fails += not ok
finally:
    srv.terminate(); srv.wait()
print(f"\n{'ALL PASS' if not fails else f'{fails} FAILED'} (API rules only; model tool-selection evals not yet implemented)")
sys.exit(1 if fails else 0)
