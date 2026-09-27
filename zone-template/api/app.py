"""Core API: auth, workflow engine, plans/confirm tokens, knowledge base search, audit. Stdlib + PyYAML.

Identity: every request needs `Authorization: Bearer <token>`. Tokens map to users (stored as SHA-256).
Writes by the AI go through plans: POST /plans -> human confirms with a one-time token -> execute.
"""
import argparse, datetime as dt, hashlib, json, pathlib, re, secrets, sqlite3, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
ZONE = yaml.safe_load((ROOT / "zone.yaml").read_text())
RANK = {r: i for i, r in enumerate(ZONE["roles"])}
TTL = int(ZONE.get("plan_ttl_seconds", 300))
DB = ROOT / "zone.db"  # overridden by --db


class ApiError(Exception):
    def __init__(self, code, msg): self.code, self.msg = code, msg


def sha(s): return hashlib.sha256(s.encode()).hexdigest()
def now(): return dt.datetime.now(dt.timezone.utc)
def iso(t): return t.strftime("%Y-%m-%d %H:%M:%S")


def db():
    c = sqlite3.connect(DB, timeout=10, isolation_level=None)  # autocommit; explicit BEGIN IMMEDIATE for writes
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init(seed=None):
    c = db()
    for f in sorted((ROOT / "schema").glob("*.sql")): c.executescript(f.read_text())
    if seed: c.executescript(pathlib.Path(seed).read_text())


def add_user(name, role, owner=None):
    if role not in RANK: sys.exit(f"unknown role {role!r}; zone roles are {ZONE['roles']}")
    c = db()
    if role == "service":
        if not owner: sys.exit("role 'service' requires --owner NAME (an existing human user)")
        o = c.execute("SELECT role FROM users WHERE name=?", (owner,)).fetchone()
        if not o or o["role"] == "service": sys.exit(f"--owner {owner!r} must be an existing human user")
    elif owner: sys.exit("--owner is only for role 'service'")
    tok = secrets.token_urlsafe(32)
    c.execute("INSERT INTO users(name,role,token_hash,owner) VALUES(?,?,?,?)", (name, role, sha(tok), owner))
    return tok


def audit(c, user, action, rid, detail):
    actor = f"{user['name']} (owner: {user['owner']})" if user["owner"] else user["name"]
    c.execute("INSERT INTO events(actor,action,record_id,detail) VALUES(?,?,?,?)", (actor, action, rid, json.dumps(detail)))


# ---- actions: the ONLY writes the API can perform. Each has check() (role + validity) and run(). ----
def _record(c, rid):
    r = c.execute("SELECT * FROM records WHERE id=?", (rid,)).fetchone()
    if not r: raise ApiError(404, f"record {rid} not found")
    return r

def _int(v, name):
    if isinstance(v, bool) or not isinstance(v, int): raise ApiError(400, f"{name} must be an integer")
    return v

def check_add_note(c, user, p):
    rid = _int(p.get("record_id"), "record_id"); _record(c, rid)
    if not isinstance(p.get("text"), str) or not p["text"].strip(): raise ApiError(400, "text is required")
    return f"Add note to record #{rid}: {p['text'][:200]!r}"

def run_add_note(c, user, p):
    c.execute("UPDATE records SET notes = notes || ? || char(10), updated=CURRENT_TIMESTAMP WHERE id=?",
              (f"[{user['name']}] {p['text']}", p["record_id"]))
    audit(c, user, "add_note", p["record_id"], p); return {"ok": True}

def check_advance_stage(c, user, p):
    rid = _int(p.get("record_id"), "record_id"); r = _record(c, rid)
    st = ZONE["stages"]; i = st.index(r["stage"])
    if i == len(st) - 1: raise ApiError(409, "already at final stage")
    nxt = st[i + 1]; need = ZONE.get("gated_transitions", {}).get(nxt)
    if need and RANK[user["role"]] < RANK[need]: raise ApiError(403, f"moving to {nxt} requires {need}")
    return f"Advance record #{rid} ({r['title']}) from {r['stage']} to {nxt}"

def run_advance_stage(c, user, p):
    summary = check_advance_stage(c, user, p)  # re-check inside the transaction
    r = _record(c, p["record_id"]); nxt = ZONE["stages"][ZONE["stages"].index(r["stage"]) + 1]
    c.execute("UPDATE records SET stage=?, updated=CURRENT_TIMESTAMP WHERE id=?", (nxt, p["record_id"]))
    audit(c, user, "advance_stage", p["record_id"], {"from": r["stage"], "to": nxt}); return {"ok": True, "stage": nxt}

ACTIONS = {"add_note": (check_add_note, run_add_note), "advance_stage": (check_advance_stage, run_advance_stage)}


def execute(c, user, action, params):
    check, run = ACTIONS[action]
    c.execute("BEGIN IMMEDIATE")
    try:
        check(c, user, params); out = run(c, user, params); c.execute("COMMIT"); return out
    except Exception:
        c.execute("ROLLBACK"); raise


class H(BaseHTTPRequestHandler):
    def send(self, code, obj):
        b = json.dumps(obj, default=dict).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def handle_safely(self, fn):
        try:
            c = db(); user = self.auth(c); self.send(200, fn(c, user, urlparse(self.path)))
        except ApiError as e: self.send(e.code, {"error": e.msg})
        except Exception as e:  # never drop the connection on bad input
            self.send(500, {"error": f"internal error: {type(e).__name__}"})

    def auth(self, c):
        h = self.headers.get("Authorization", "")
        if not h.startswith("Bearer ") or not h[7:]: raise ApiError(401, "sign in required: Authorization: Bearer <token>")
        u = c.execute("SELECT name, role, owner FROM users WHERE token_hash=?", (sha(h[7:]),)).fetchone()
        if not u: raise ApiError(401, "invalid token")
        if u["role"] not in RANK: raise ApiError(403, "role not valid in this zone")
        return u

    def body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            b = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, UnicodeDecodeError): raise ApiError(400, "body must be valid JSON")
        if not isinstance(b, dict): raise ApiError(400, "body must be a JSON object")
        return b

    def do_GET(self): self.handle_safely(self.get)
    def do_POST(self): self.handle_safely(self.post)

    def get(self, c, user, u):
        q = parse_qs(u.query)
        if u.path == "/zone": return ZONE
        if u.path == "/whoami": return dict(user)
        if u.path in ("/records", "/kb"):
            s = f"%{q.get('q', [''])[0]}%"
            sql = ("SELECT * FROM records WHERE title LIKE ? OR notes LIKE ? ORDER BY id" if u.path == "/records"
                   else "SELECT id,title,body FROM kb WHERE title LIKE ? OR body LIKE ?")
            return [dict(r) for r in c.execute(sql, (s, s))]
        if m := re.fullmatch(r"/records/(\d+)", u.path): return dict(_record(c, int(m[1])))
        if m := re.fullmatch(r"/plans/(\d+)", u.path):
            p = c.execute("SELECT id,actor,action,params,summary,status,created,expires_at,result FROM plans WHERE id=?", (m[1],)).fetchone()
            if not p: raise ApiError(404, "plan not found")
            if p["actor"] != user["name"] and RANK[user["role"]] < RANK["lead"]: raise ApiError(403, "not your plan")
            return dict(p)
        if u.path == "/events":
            if RANK[user["role"]] < RANK["lead"]: raise ApiError(403, "audit log requires lead")
            return [dict(r) for r in c.execute("SELECT * FROM events ORDER BY id DESC LIMIT 50")]
        raise ApiError(404, "no route")

    def post(self, c, user, u):
        b = self.body()
        if u.path == "/plans":
            action, params = b.get("action"), b.get("params", {})
            if action not in ACTIONS: raise ApiError(400, f"unknown action; allowed: {sorted(ACTIONS)}")
            if not isinstance(params, dict): raise ApiError(400, "params must be an object")
            summary = ACTIONS[action][0](c, user, params)  # validates params and role now
            tok = secrets.token_urlsafe(32)
            cur = c.execute("INSERT INTO plans(actor,action,params,summary,token_hash,expires_at) VALUES(?,?,?,?,?,?)",
                            (user["name"], action, json.dumps(params), summary, sha(tok), iso(now() + dt.timedelta(seconds=TTL))))
            audit(c, user, "plan_created", params.get("record_id"), {"plan_id": cur.lastrowid, "action": action})
            return {"plan_id": cur.lastrowid, "summary": summary, "confirm_token": tok, "expires_in_s": TTL}
        if m := re.fullmatch(r"/plans/(\d+)/confirm", u.path):
            tok = b.get("confirm_token")
            if not isinstance(tok, str) or not tok: raise ApiError(400, "confirm_token is required")
            c.execute("BEGIN IMMEDIATE")
            try:
                p = c.execute("SELECT * FROM plans WHERE id=?", (m[1],)).fetchone()
                if not p: raise ApiError(404, "plan not found")
                if p["actor"] != user["name"]: raise ApiError(403, "only the user who requested the plan can confirm it")
                if not secrets.compare_digest(p["token_hash"], sha(tok)): raise ApiError(403, "confirm token does not match")
                if p["status"] != "pending": raise ApiError(410, f"plan already {p['status']}")
                if iso(now()) >= p["expires_at"]:
                    c.execute("UPDATE plans SET status='expired' WHERE id=?", (p["id"],)); c.execute("COMMIT")
                    raise ApiError(410, "confirm token expired")
                params = json.loads(p["params"]); check, run = ACTIONS[p["action"]]
                try:
                    check(c, user, params)  # the role must STILL allow it at confirm time
                    out = run(c, user, params)
                except ApiError as e:
                    c.execute("UPDATE plans SET status='failed', result=? WHERE id=?", (e.msg, p["id"])); c.execute("COMMIT"); raise
                c.execute("UPDATE plans SET status='executed', result=? WHERE id=?", (json.dumps(out), p["id"]))
                audit(c, user, "plan_executed", params.get("record_id"), {"plan_id": p["id"]})
                c.execute("COMMIT"); return {"plan_id": p["id"], "status": "executed", "result": out}
            except ApiError:
                if c.in_transaction: c.execute("ROLLBACK")
                raise
        # Direct writes for the human-operated UI (same checks, no plan). The AI has no tool for these.
        if m := re.fullmatch(r"/records/(\d+)/(notes|advance)", u.path):
            action = "add_note" if m[2] == "notes" else "advance_stage"
            return execute(c, user, action, {"record_id": int(m[1]), **({"text": b.get("text")} if action == "add_note" else {})})
        raise ApiError(404, "no route")

    def log_message(self, *a): pass


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--db"); p.add_argument("--seed", help="reset the DB and load this seed file")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--add-user", nargs=2, metavar=("NAME", "ROLE")); p.add_argument("--owner")
    a = p.parse_args()
    if a.db: DB = pathlib.Path(a.db)
    if a.seed:
        for suffix in ("", "-wal", "-shm"): pathlib.Path(str(DB) + suffix).unlink(missing_ok=True)
    init(a.seed)
    if a.add_user:
        tok = add_user(*a.add_user, owner=a.owner)
        print(f"Created {a.add_user[0]} ({a.add_user[1]}). Token (shown once, store it safely):\n{tok}"); sys.exit(0)
    print(f"{ZONE['title']} API on http://127.0.0.1:{a.port}")
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
