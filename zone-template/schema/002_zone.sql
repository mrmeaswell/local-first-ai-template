-- Zone-specific tables. Replace these for your zone.
CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY, title TEXT NOT NULL, stage TEXT NOT NULL,
  owner TEXT, notes TEXT DEFAULT '', updated TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS kb (id TEXT PRIMARY KEY, title TEXT, body TEXT);
