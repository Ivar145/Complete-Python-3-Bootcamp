import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "leads.db")

DEFAULT_TEMPLATES = [
    (
        "No Website - Cold Outreach",
        "Quick question about {business_name}'s online presence",
        """Hi {owner_name},

I was searching for {category} services in {city} and noticed that {business_name} doesn't have a website yet.

A lot of potential customers in {city} search Google before deciding where to go — without a website, {business_name} is invisible to them. I help small businesses like yours get online quickly with a clean, professional WordPress site that shows up in local searches.

Would you be open to a quick chat about what that could look like for {business_name}?

Best,
{your_name}""",
    ),
    (
        "Poor SEO - Cold Outreach",
        "{business_name}'s website might be costing you customers",
        """Hi {owner_name},

I came across {business_name}'s website and noticed something that's likely hurting your Google ranking: {issue}.

This is a common issue for {category} businesses in {city}, and the good news is it's fixable. I specialize in WordPress SEO improvements that help local businesses rank higher and get more calls from Google.

Would you be interested in a free 10-minute review of your site?

Best,
{your_name}""",
    ),
    (
        "Follow-up (2 weeks)",
        "Re: {business_name}'s website",
        """Hi {owner_name},

Just following up on my last message in case it got buried.

I know running a {category} business keeps you busy — I'll keep this short. If you're interested in getting more customers from Google, I'd love to help {business_name} get there.

Happy to answer any questions whenever it's convenient.

Best,
{your_name}""",
    ),
    (
        "Second Follow-up",
        "Last note — {business_name}",
        """Hi {owner_name},

I won't keep cluttering your inbox — this is my last note.

If things change and {business_name} ever wants to explore getting a website or improving your Google presence, feel free to reach out. I'm always happy to help {category} businesses in {city}.

Wishing you all the best,
{your_name}""",
    ),
]

DEFAULT_SETTINGS = {
    "your_name": "",
    "gmail_address": "",
    "gmail_app_password": "",
    "google_places_api_key": "",
    "follow_up_days": "14",
}


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                address TEXT,
                phone TEXT,
                website TEXT,
                contact_email TEXT,
                category TEXT,
                location TEXT,
                priority INTEGER,
                contact_name TEXT,
                contact_method TEXT DEFAULT 'email',
                status TEXT DEFAULT 'new',
                seo_score INTEGER,
                seo_issues TEXT,
                notes TEXT,
                revenue REAL,
                last_contacted_at TEXT,
                email_thread_id TEXT,
                follow_up_count INTEGER DEFAULT 0,
                google_maps_url TEXT,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                subject TEXT,
                body TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER REFERENCES leads(id),
                name TEXT,
                start_date TEXT,
                deadline TEXT,
                status TEXT DEFAULT 'in_progress',
                notes TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS email_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER REFERENCES leads(id),
                subject TEXT,
                body TEXT,
                message_id TEXT,
                sent_at TEXT
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)

        row = conn.execute("SELECT COUNT(*) FROM templates").fetchone()
        if row[0] == 0:
            now = datetime.utcnow().isoformat()
            conn.executemany(
                "INSERT INTO templates (name, subject, body, created_at) VALUES (?, ?, ?, ?)",
                [(t[0], t[1], t[2], now) for t in DEFAULT_TEMPLATES],
            )

        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )


def get_setting(key: str) -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else ""


def save_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )


def get_all_settings() -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {row["key"]: row["value"] for row in rows}


def add_lead(lead_dict: dict) -> int:
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM leads WHERE name = ? AND location = ?",
            (lead_dict.get("name", ""), lead_dict.get("location", "")),
        ).fetchone()
        if existing:
            return existing["id"]

        now = datetime.utcnow().isoformat()
        cursor = conn.execute(
            """INSERT INTO leads
               (name, address, phone, website, contact_email, category, location, priority,
                contact_name, contact_method, status, seo_score, seo_issues, notes, revenue,
                last_contacted_at, email_thread_id, follow_up_count, google_maps_url, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lead_dict.get("name", ""),
                lead_dict.get("address", ""),
                lead_dict.get("phone", ""),
                lead_dict.get("website", ""),
                lead_dict.get("contact_email", ""),
                lead_dict.get("category", ""),
                lead_dict.get("location", ""),
                lead_dict.get("priority"),
                lead_dict.get("contact_name", ""),
                lead_dict.get("contact_method", "email"),
                lead_dict.get("status", "new"),
                lead_dict.get("seo_score"),
                lead_dict.get("seo_issues"),
                lead_dict.get("notes", ""),
                lead_dict.get("revenue"),
                lead_dict.get("last_contacted_at"),
                lead_dict.get("email_thread_id"),
                lead_dict.get("follow_up_count", 0),
                lead_dict.get("google_maps_url", ""),
                now,
                now,
            ),
        )
        return cursor.lastrowid


def get_leads(status: str = None, priority: int = None, search: str = None, category: str = None) -> list:
    query = "SELECT * FROM leads WHERE 1=1"
    params = []

    if status:
        query += " AND status = ?"
        params.append(status)
    if priority:
        query += " AND priority = ?"
        params.append(priority)
    if category:
        query += " AND category = ?"
        params.append(category)
    if search:
        query += " AND (name LIKE ? OR address LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    query += " ORDER BY created_at DESC"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def get_categories() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT category FROM leads WHERE category != '' ORDER BY category"
        ).fetchall()
        return [row["category"] for row in rows]


def get_lead(lead_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return dict(row) if row else None


def update_lead(lead_id: int, **kwargs):
    if not kwargs:
        return
    kwargs["updated_at"] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [lead_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE leads SET {set_clause} WHERE id = ?", values)


def delete_lead(lead_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM email_log WHERE lead_id = ?", (lead_id,))
        conn.execute("DELETE FROM projects WHERE lead_id = ?", (lead_id,))
        conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))


def get_templates() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM templates ORDER BY id").fetchall()
        return [dict(row) for row in rows]


def get_template(template_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()
        return dict(row) if row else None


def save_template(name: str, subject: str, body: str, template_id: int = None) -> int:
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        if template_id:
            conn.execute(
                "UPDATE templates SET name = ?, subject = ?, body = ? WHERE id = ?",
                (name, subject, body, template_id),
            )
            return template_id
        else:
            cursor = conn.execute(
                "INSERT INTO templates (name, subject, body, created_at) VALUES (?, ?, ?, ?)",
                (name, subject, body, now),
            )
            return cursor.lastrowid


def delete_template(template_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM templates WHERE id = ?", (template_id,))


def add_email_log(lead_id: int, subject: str, body: str, message_id: str):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO email_log (lead_id, subject, body, message_id, sent_at) VALUES (?, ?, ?, ?, ?)",
            (lead_id, subject, body, message_id, now),
        )


def get_email_log(lead_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM email_log WHERE lead_id = ? ORDER BY sent_at DESC",
            (lead_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_projects() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT p.*, l.name as lead_name FROM projects p JOIN leads l ON p.lead_id = l.id ORDER BY p.created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def get_project(lead_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE lead_id = ? ORDER BY created_at DESC LIMIT 1",
            (lead_id,),
        ).fetchone()
        return dict(row) if row else None


def save_project(lead_id: int, name: str, start_date: str, deadline: str, status: str, notes: str):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM projects WHERE lead_id = ?", (lead_id,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE projects SET name = ?, start_date = ?, deadline = ?, status = ?, notes = ? WHERE lead_id = ?",
                (name, start_date, deadline, status, notes, lead_id),
            )
        else:
            conn.execute(
                "INSERT INTO projects (lead_id, name, start_date, deadline, status, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (lead_id, name, start_date, deadline, status, notes, now),
            )


def mark_replies_received(lead_ids: list):
    if not lead_ids:
        return
    placeholders = ",".join("?" * len(lead_ids))
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            f"UPDATE leads SET status = 'replied', updated_at = ? WHERE id IN ({placeholders})",
            [now] + lead_ids,
        )


def auto_flag_followups(follow_up_days: int):
    cutoff = (datetime.utcnow() - timedelta(days=follow_up_days)).isoformat()
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            """UPDATE leads SET status = 'follow_up', updated_at = ?
               WHERE status = 'contacted' AND last_contacted_at < ? AND last_contacted_at IS NOT NULL""",
            (now, cutoff),
        )
