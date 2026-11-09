"""Tiny database layer: SQLite locally, PostgreSQL on Render (DATABASE_URL)."""
import os
import sqlite3
from flask import g

URL = os.environ.get("DATABASE_URL", "sqlite:///leadgen.db")
if URL.startswith("postgres://"):
    URL = "postgresql://" + URL[len("postgres://"):]
PG = URL.startswith("postgresql")


def get():
    if "db" not in g:
        if PG:
            import psycopg
            from psycopg.rows import dict_row
            g.db = psycopg.connect(URL, row_factory=dict_row)
        else:
            g.db = sqlite3.connect(URL.replace("sqlite:///", ""))
            g.db.row_factory = sqlite3.Row
    return g.db


def close(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def q(sql, args=(), one=False):
    """Run a query and return rows as dicts. Use ? for parameters."""
    conn = get()
    if PG:
        sql = sql.replace("?", "%s")
    cur = conn.execute(sql, args)
    rows = [dict(r) for r in cur.fetchall()] if cur.description else []
    if one:
        return rows[0] if rows else None
    return rows


def x(sql, args=()):
    """Run a write and commit. Returns the first row when the SQL uses RETURNING."""
    try:
        rows = q(sql, args)
        get().commit()
    except Exception:
        get().rollback()
        raise
    return rows[0] if rows else None


PK = "SERIAL PRIMARY KEY" if PG else "INTEGER PRIMARY KEY AUTOINCREMENT"
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS contractors (
  id {PK}, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, phone TEXT DEFAULT '',
  password_hash TEXT, is_house INTEGER DEFAULT 0, services TEXT DEFAULT '', cities TEXT DEFAULT '',
  plan TEXT DEFAULT 'perlead', cap INTEGER DEFAULT 8, sms_alerts INTEGER DEFAULT 1,
  paused INTEGER DEFAULT 0, active INTEGER DEFAULT 1, stripe_customer TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS leads (
  id {PK}, created_at TEXT NOT NULL, name TEXT NOT NULL, phone TEXT NOT NULL, email TEXT DEFAULT '',
  zip TEXT NOT NULL, city TEXT, service TEXT NOT NULL, size TEXT, timeline TEXT, budget TEXT, notes TEXT DEFAULT '',
  consent INTEGER DEFAULT 0, consent_text TEXT, consent_version TEXT, ip TEXT, user_agent TEXT, page TEXT,
  score INTEGER, tier TEXT, contractor_id INTEGER, kept INTEGER DEFAULT 0, price INTEGER DEFAULT 0,
  status TEXT, route_note TEXT, billed_invoice TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS leads_contractor ON leads (contractor_id, created_at);
CREATE TABLE IF NOT EXISTS events (
  id {PK}, created_at TEXT NOT NULL, kind TEXT, text TEXT, lead_id INTEGER
);
CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT)
"""


def init_schema():
    conn = get()
    for stmt in SCHEMA.split(";"):
        if stmt.strip():
            conn.execute(stmt)
    conn.commit()
