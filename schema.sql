-- schema.sql
-- =====================================================
-- PHISHING SIMULATION AWARENESS PLATFORM (SQLite Schema)
-- =====================================================

-- ---------- USERS ----------
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    email TEXT
);

-- Default admin user (plaintext initially, migrated on first login)
INSERT OR IGNORE INTO users (username, password, email)
VALUES ('admin', 'admin123', 'admin@example.com');

-- ---------- CAMPAIGNS ----------
CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    template TEXT,
    status TEXT DEFAULT 'draft',
    created_at TEXT DEFAULT (datetime('now'))
);

-- ---------- TARGETS ----------
CREATE TABLE IF NOT EXISTS targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER,
    name TEXT,
    email TEXT NOT NULL,
    department TEXT DEFAULT 'N/A',
    token TEXT UNIQUE,
    clicked INTEGER DEFAULT 0,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
);

-- ---------- SENDS ----------
CREATE TABLE IF NOT EXISTS sends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER,
    target_id INTEGER,
    sent_at TEXT,
    provider TEXT,
    status TEXT,
    details TEXT,
    FOREIGN KEY (target_id) REFERENCES targets(id) ON DELETE CASCADE,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
);

-- ---------- CLICKS ----------
CREATE TABLE IF NOT EXISTS clicks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id INTEGER,
    campaign_id INTEGER,
    ts TEXT,
    FOREIGN KEY (target_id) REFERENCES targets(id) ON DELETE CASCADE,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
);
