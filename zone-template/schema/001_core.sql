-- Standard core tables (every zone). Do not fork.
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, role TEXT NOT NULL,
  token_hash TEXT UNIQUE,            -- SHA-256 of the bearer token; the token itself is never stored
  owner TEXT);                       -- required for role 'service': the accountable human user
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, ts TEXT DEFAULT CURRENT_TIMESTAMP,
  actor TEXT, action TEXT, record_id INTEGER, detail TEXT);
CREATE TABLE IF NOT EXISTS attachments (id INTEGER PRIMARY KEY, record_id INTEGER, path TEXT);
CREATE TABLE IF NOT EXISTS config_versions (id INTEGER PRIMARY KEY, ts TEXT DEFAULT CURRENT_TIMESTAMP, key TEXT, value TEXT);
CREATE TABLE IF NOT EXISTS host_action_log (id INTEGER PRIMARY KEY, ts TEXT DEFAULT CURRENT_TIMESTAMP, action TEXT, result TEXT);
CREATE TABLE IF NOT EXISTS plans (id INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL,
  params TEXT NOT NULL, summary TEXT, token_hash TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',  -- pending|executed|expired|stale|failed
  created TEXT DEFAULT CURRENT_TIMESTAMP, expires_at TEXT NOT NULL, result TEXT,
  snapshot TEXT,        -- hash of the record(s) the plan depends on; any change -> stale
  payload_hash TEXT);   -- hash of (action, resolved params, summary shown, snapshot)
