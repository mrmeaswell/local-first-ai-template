"""Deterministic eval runner (Section 13). Negative suite must be 100%."""
import json, pathlib, httpx, sys
API = "http://127.0.0.1:8080"; D = pathlib.Path(__file__).parent; fails = 0
def call(c, role="lead", body=None):
    return httpx.request(c[0], API + c[1], json=body, headers={"X-User": "eval", "X-Role": role})
for line in (D / "golden.jsonl").read_text().splitlines():
    t = json.loads(line); r = call(t["call"]).json(); ok = True
    if "expect" in t: ok = all(r.get(k) == v for k, v in t["expect"].items())
    if "expect_contains_id" in t: ok = any(x["id"] == t["expect_contains_id"] for x in r)
    if "expect_min_len" in t: ok = len(r) >= t["expect_min_len"]
    print(("PASS" if ok else "FAIL"), "golden", t["id"]); fails += not ok
for line in (D / "negative.jsonl").read_text().splitlines():
    t = json.loads(line); r = call(t["call"], t["role"], t.get("body")); ok = r.status_code == t["expect_status"]
    print(("PASS" if ok else "FAIL"), "negative", t["id"], "-", t["desc"]); fails += not ok
print(f"\n{'ALL PASS' if not fails else f'{fails} FAILED'}"); sys.exit(1 if fails else 0)
