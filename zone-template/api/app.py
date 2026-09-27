"""Core API: auth, workflow engine, plans/confirm tokens, knowledge base search, audit. Stdlib + PyYAML.

Identity: every request needs `Authorization: Bearer <token>`. Tokens map to users (stored as SHA-256).
Writes by the AI go through plans: POST /plans -> human confirms with a one-time token -> execute.

Plan integrity:
- A plan stores the exact, fully resolved change (e.g. from_stage -> to_stage), never "the next stage".
- A plan stores a snapshot hash of the record it touches. Any change to that record before confirm -> 409 stale.
- The approval summary shows every field that will be written, untruncated. A hash of (action, params, summary)
  is stored; confirm writes only if it still matches.
- Who may view the audit log, view others' plans, confirm plans, and request host actions comes from
  zone.yaml `permissions`. There are no role names in this file.
"""
import argparse, datetime as dt, hashlib, json, os, pathlib, re, secrets, sqlite3, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
ZONE_FILE = pathlib.Path(os.environ.get("ZONE_CONFIG", ROOT / "zone.yaml"))
DB = ROOT / "zone.db"  # overridden by --db
MAX_TEXT = 2000        # longest free-text field accepted; the approval prompt always shows it in full


class ConfigError(SystemExit): pass


def load_zone(path):
    z = yaml.safe_load(pathlib.Path(path).read_text())
    roles = z.get("roles") or []
    if not roles or len(set(roles)) != len(roles): raise ConfigError(f"{path}: roles must be a non-empty list of unique names")
    top = [roles[-1]]
    perms = {k: z.get("permissions", {}).get(k, top) for k in ("view_audit", "view_others_plans", "approve", "host_actions")}
    unknown_perm = set(z.get("permissions", {})) - set(perms)
    if unknown_perm: raise ConfigError(f"{path}: unknown permissions {sorted(unknown_perm)}")
    for k, v in perms.items():
        if not isinstance(v, list): raise ConfigError(f"{path}: permissions.{k} must be a list of roles")
        bad = set(v) - set(roles)
        if bad: raise ConfigError(f"{path}: permissions.{k} names undefined role(s) {sorted(bad)}; zone roles are {roles}")
    for stage, role in (z.get("gated_transitions") or {}).items():
        if stage not in z.get("stages", []): raise ConfigError(f"{path}: gated_transitions names undefined stage {stage!r}")
        if role not in roles: raise ConfigError(f"{path}: gated_transitions.{stage} names undefined role {role!r}; zone roles are {roles}")
    bad = set(z.setdefault("service_roles", [])) - set(roles)
    if bad: raise ConfigError(f"{path}: service_roles names undefined role(s) {sorted(bad)}; zone roles are {roles}")
    z["permissions"] = perms
    return z


ZONE = load_zone(ZONE_FILE)
RANK = {r: i for i, r in enumerate(ZONE["roles"])}
PERM = ZONE["permissions"]
TTL = int(ZONE.get("plan_ttl_seconds", 300))


class ApiError(Exception):
    def __init__(self, code, msg): self.code, self.msg = code, msg


def sha(s): return hashlib.sha256(s.encode()).hexdigest()
def canon(o): return json.dumps(o, sort_keys=True, separators=(",", ":"))
def now(): return dt.datetime.now(dt.timezone.utc)
def iso(t): return t.strftime("%Y-%m-%d %H:%M:%S")
def allowed(user, perm): return user["role"] in PERM[perm]


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
    if role not in RANK: raise SystemExit(f"unknown role {role!r}; zone roles are {ZONE['roles']}")
    c = db()
    if role in ZONE["service_roles"]:
        if not owner: raise SystemExit(f"role {role!r} is a service role and requires --owner NAME (an existing human user)")
        o = c.execute("SELECT role FROM users WHERE name=?", (owner,)).fetchone()
        if not o or o["role"] in ZONE["service_roles"]: raise SystemExit(f"--owner {owner!r} must be an existing human user")
    elif owner: raise SystemExit("--owner is only for service roles")
    tok = secrets.token_urlsafe(32)
    c.execute("INSERT INTO users(name,role,token_hash,owner) VALUES(?,?,?,?)", (name, role, sha(tok), owner))
    return tok


def audit(c, user, action, rid, detail):
    actor = f"{user['name']} (owner: {user['owner']})" if user["owner"] else user["name"]
    c.execute("INSERT INTO events(actor,action,record_id,detail) VALUES(?,?,?,?)", (actor, action, rid, json.dumps(detail)))


# ---- actions -------------------------------------------------------------------------------------------
# An action is a dict: check(c, user, params) -> (summary, resolved_params); run(c, user, resolved) -> result;
# optional snapshot(c, resolved) -> str (anything the plan depends on; a change makes the plan stale).
# check() must resolve everything run() will do, so run() never decides anything new at confirm time.
def _record(c, rid):
    r = c.execute("SELECT * FROM records WHERE id=?", (rid,)).fetchone()
    if not r: raise ApiError(404, f"record {rid} not found")
    return r

def _int(v, name):
    if isinstance(v, bool) or not isinstance(v, int): raise ApiError(400, f"{name} must be an integer")
    return v

def _snapshot_record(c, p): return sha(canon(dict(_record(c, p["record_id"]))))

def check_add_note(c, user, p):
    if set(p) - {"record_id", "text"}: raise ApiError(400, "add_note accepts only record_id and text")
    rid = _int(p.get("record_id"), "record_id"); _record(c, rid)
    t = p.get("text")
    if not isinstance(t, str) or not t.strip(): raise ApiError(400, "text is required")
    if len(t) > MAX_TEXT: raise ApiError(422, f"note exceeds {MAX_TEXT} chars")
    return f"Add note to record #{rid}. Full text ({len(t)} chars):\n{t}", {"record_id": rid, "text": t}

def run_add_note(c, user, p):
    c.execute("UPDATE records SET notes = notes || ? || char(10), updated=CURRENT_TIMESTAMP WHERE id=?",
              (f"[{user['name']}] {p['text']}", p["record_id"]))
    audit(c, user, "add_note", p["record_id"], p); return {"ok": True}

def check_advance_stage(c, user, p):
    if set(p) - {"record_id", "from_stage", "to_stage"}: raise ApiError(400, "advance_stage accepts only record_id")
    rid = _int(p.get("record_id"), "record_id"); r = _record(c, rid)
    st = ZONE["stages"]; i = st.index(r["stage"])
    if "from_stage" in p and p["from_stage"] != r["stage"]: raise ApiError(409, "record changed, re-plan")
    if i == len(st) - 1: raise ApiError(409, "already at final stage")
    nxt = st[i + 1]
    if "to_stage" in p and p["to_stage"] != nxt: raise ApiError(409, "record changed, re-plan")
    need = ZONE.get("gated_transitions", {}).get(nxt)
    if need and RANK[user["role"]] < RANK[need]: raise ApiError(403, f"moving to {nxt} requires {need}")
    return (f"Advance record #{rid} ({r['title']}) from {r['stage']} to {nxt}",
            {"record_id": rid, "from_stage": r["stage"], "to_stage": nxt})

def run_advance_stage(c, user, p):
    cur = c.execute("UPDATE records SET stage=?, updated=CURRENT_TIMESTAMP WHERE id=? AND stage=?",
                    (p["to_stage"], p["record_id"], p["from_stage"]))  # exact transition only
    if cur.rowcount != 1: raise ApiError(409, "record changed, re-plan")
    audit(c, user, "advance_stage", p["record_id"], {"from": p["from_stage"], "to": p["to_stage"]})
    return {"ok": True, "stage": p["to_stage"]}

ACTIONS = {
    "add_note": {"check": check_add_note, "run": run_add_note, "snapshot": _snapshot_record},
    "advance_stage": {"check": check_advance_stage, "run": run_advance_stage, "snapshot": _snapshot_record},
}

# ---- host actions via the privileged helper (Unix socket). Only roles in permissions.host_actions. ----
def _helper(op, **kw):
    sys.path.insert(0, str(ROOT / "helper")); import client
    try: return client.call(op, **kw)
    except client.HelperError as e: raise ApiError(e.code, e.msg)
    except OSError as e: raise ApiError(503, f"helper unavailable: {e}")

def check_host_action(c, user, p):
    if not allowed(user, "host_actions"): raise ApiError(403, "host actions require one of " + ", ".join(PERM["host_actions"]))
    if set(p) - {"action_id", "params"} or not isinstance(p.get("action_id"), str): raise ApiError(400, "host_action needs action_id and optional params")
    params = p.get("params") or {}
    if not isinstance(params, dict): raise ApiError(400, "params must be an object")
    return _helper("plan", action_id=p["action_id"], params=params), {"action_id": p["action_id"], "params": params}

def run_host_action(c, user, p):
    h = _helper("apply", action_id=p["action_id"], params=p["params"])
    c.execute("INSERT INTO host_action_log(action,result) VALUES(?,?)", (p["action_id"], json.dumps(h)))
    audit(c, user, "host_action", None, {"action_id": p["action_id"], "handle": h}); return {"ok": True, "handle": h}

ACTIONS["host_action"] = {"check": check_host_action, "run": run_host_action}

# ---- zone extension hook: an optional zone_actions.py at the zone root may add actions and read routes ----
ZONE_GET = None
if (ROOT / "zone_actions.py").exists():
    sys.path.insert(0, str(ROOT)); import zone_actions as _za
    _za.bind(ApiError=ApiError, audit=audit, ZONE=ZONE, RANK=RANK, PERM=PERM, allowed=allowed)
    if getattr(_za, "REPLACE_DEFAULT_ACTIONS", False): ACTIONS = {k: v for k, v in ACTIONS.items() if k == "host_action"}
    ACTIONS.update(_za.ACTIONS); ZONE_GET = getattr(_za, "get", None)


def _check(c, user, action, params):
    out = ACTIONS[action]["check"](c, user, params)
    return out if isinstance(out, tuple) else (out, params)

def _snap(c, action, resolved):
    fn = ACTIONS[action].get("snapshot")
    return fn(c, resolved) if fn else ""

def payload_hash(action, resolved, summary, snapshot):
    return sha(canon({"action": action, "params": resolved, "summary": summary, "snapshot": snapshot}))


def execute(c, user, action, params):
    c.execute("BEGIN IMMEDIATE")
    try:
        _, resolved = _check(c, user, action, params); out = ACTIONS[action]["run"](c, user, resolved)
        c.execute("COMMIT"); return out
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
        if m := re.fullmatch(r"/plans/(\d+)", u.path):
            p = c.execute("SELECT id,actor,action,params,summary,status,created,expires_at,result FROM plans WHERE id=?", (m[1],)).fetchone()
            if not p: raise ApiError(404, "plan not found")
            if p["actor"] != user["name"] and not allowed(user, "view_others_plans"): raise ApiError(403, "not your plan")
            return dict(p)
        if u.path == "/events":
            if not allowed(user, "view_audit"): raise ApiError(403, "audit log requires one of " + ", ".join(PERM["view_audit"]))
            return [dict(r) for r in c.execute("SELECT * FROM events ORDER BY id DESC LIMIT 50")]
        if ZONE_GET:
            out = ZONE_GET(c, user, u.path, q)
            if out is not None: return out
        if u.path in ("/records", "/kb"):
            s = f"%{q.get('q', [''])[0]}%"
            sql = ("SELECT * FROM records WHERE title LIKE ? OR notes LIKE ? ORDER BY id" if u.path == "/records"
                   else "SELECT id,title,body FROM kb WHERE title LIKE ? OR body LIKE ?")
            return [dict(r) for r in c.execute(sql, (s, s))]
        if m := re.fullmatch(r"/records/(\d+)", u.path): return dict(_record(c, int(m[1])))
        raise ApiError(404, "no route")

    def post(self, c, user, u):
        b = self.body()
        if u.path == "/plans":
            action, params = b.get("action"), b.get("params", {})
            if action not in ACTIONS: raise ApiError(400, f"unknown action; allowed: {sorted(ACTIONS)}")
            if not isinstance(params, dict): raise ApiError(400, "params must be an object")
            summary, resolved = _check(c, user, action, params)  # validates params and role, resolves the exact change
            snap = _snap(c, action, resolved); tok = secrets.token_urlsafe(32)
            cur = c.execute("INSERT INTO plans(actor,action,params,summary,token_hash,expires_at,snapshot,payload_hash) VALUES(?,?,?,?,?,?,?,?)",
                            (user["name"], action, canon(resolved), summary, sha(tok), iso(now() + dt.timedelta(seconds=TTL)),
                             snap, payload_hash(action, resolved, summary, snap)))
            audit(c, user, "plan_created", resolved.get("record_id"), {"plan_id": cur.lastrowid, "action": action})
            return {"plan_id": cur.lastrowid, "summary": summary, "confirm_token": tok, "expires_in_s": TTL}
        if m := re.fullmatch(r"/plans/(\d+)/confirm", u.path):
            tok = b.get("confirm_token")
            if not isinstance(tok, str) or not tok: raise ApiError(400, "confirm_token is required")
            c.execute("BEGIN IMMEDIATE")
            def close(status, result, code, msg):
                c.execute("UPDATE plans SET status=?, result=? WHERE id=?", (status, result, int(m[1]))); c.execute("COMMIT")
                raise ApiError(code, msg)
            try:
                p = c.execute("SELECT * FROM plans WHERE id=?", (m[1],)).fetchone()
                if not p: raise ApiError(404, "plan not found")
                if p["actor"] != user["name"]: raise ApiError(403, "only the user who requested the plan can confirm it")
                if not allowed(user, "approve"): raise ApiError(403, "your role may not approve plans")
                if not secrets.compare_digest(p["token_hash"], sha(tok)): raise ApiError(403, "confirm token does not match")
                if p["status"] != "pending": raise ApiError(410, f"plan already {p['status']}")
                if iso(now()) >= p["expires_at"]: close("expired", None, 410, "confirm token expired")
                params = json.loads(p["params"])
                if not secrets.compare_digest(p["payload_hash"] or "", payload_hash(p["action"], params, p["summary"], p["snapshot"])):
                    close("failed", "payload changed after approval was requested", 409, "payload changed, re-plan")
                if _snap(c, p["action"], params) != p["snapshot"]:
                    close("stale", "record changed since plan", 409, "record changed, re-plan")
                try:
                    _check(c, user, p["action"], params)  # the role must STILL allow it at confirm time
                    out = ACTIONS[p["action"]]["run"](c, user, params)
                except ApiError as e:
                    close("stale" if e.code == 409 else "failed", e.msg, e.code, e.msg)
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
