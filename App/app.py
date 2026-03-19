"""
SAI - AI Chat Application
Works on Windows and Linux (Mint/Ubuntu)
"""
import os
import sys
import sqlite3
import hashlib
import secrets
import base64
import smtplib
import json
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
from datetime import date, datetime
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory, session, redirect, Response
from groq import Groq
import stripe
import requests as http_requests

# ── BASE PATH (works on Windows + Linux) ─────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()

# ── APP ───────────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=str(BASE_DIR / 'static'))
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20MB

# ── CONFIG (edit these) ───────────────────────────────────────────────────────
app.secret_key        = "6e411d59e49dc9e02f4d2b28c78fe27c80e8eef0edfb6f5bc42d733834264a5f"
GROQ_API_KEY          = "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"
FAL_API_KEY           = "2fddd6d4-c32f-4bcb-bc41-5844d3c65218:406d3327f7210e2b35a631fafd855b29"          # fal.ai — free tier available
stripe.api_key        = "sk_test_51T9tysFWsQqbbESZrQguglAhKmbDZNP3jDOfGoliQYjd7Ealyysa63f1aVw1OejtMOTJbxic5AeFTsT3yKLZYESs004F6QR2B3"
STRIPE_PUB_KEY        = "pk_test_51T9tysFWsQqbbESZxomtwbPEcYLFq4Ta24HVozcPYtchVKR8OhXpJlwIPCkiIUKwOIYUctaOyzB8OMkp6SKUMB8d00IlkXkZq7"
STRIPE_PRO_PRICE_ID   = "price_1T9u0qFWsQqbbESZkN5xOmoi"
STRIPE_MAX_PRICE_ID   = "price_1T9u0dFWsQqbbESZRTheciRR"
STRIPE_WEBHOOK_SECRET = ""
BASE_URL              = "http://localhost:5000"      # change to ngrok URL for remote access
ADMIN_EMAIL           = "bahablastofficial@gmail.com"
ADMIN_PASSWORD        = "S@muel78"
ADMIN_NAME            = "Sam"
FREE_MSG_LIMIT        = 20

# SMTP — Gmail: enable 2FA, create App Password at myaccount.google.com/apppasswords
SMTP_HOST  = "smtp.gmail.com"
SMTP_PORT  = 587
SMTP_USER  = "bahablastofficial@gmail.com"
SMTP_PASS  = "YOUR_GMAIL_APP_PASSWORD"   # 16-char app password, NOT your Gmail password
SMTP_FROM  = "SAI <bahablastofficial@gmail.com>"

# OAuth — fill in when ready
GITHUB_CLIENT_ID      = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET  = os.environ.get("GITHUB_CLIENT_SECRET", "")
DISCORD_CLIENT_ID     = os.environ.get("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "")
GOOGLE_CLIENT_ID      = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET  = os.environ.get("GOOGLE_CLIENT_SECRET", "")

# ── MODELS ────────────────────────────────────────────────────────────────────
TIER_MODELS = {
    "free": [
        {"id": "llama-3.1-8b-instant", "name": "LLaMA 3.1 8B", "desc": "Fast & capable"},
    ],
    "pro": [
        {"id": "llama-3.1-8b-instant",   "name": "LLaMA 3.1 8B",  "desc": "Fast & capable"},
        {"id": "mixtral-8x7b-32768",      "name": "Mixtral 8x7B",  "desc": "Great for long context"},
        {"id": "llama-3.3-70b-versatile", "name": "LLaMA 3.3 70B", "desc": "Most powerful"},
    ],
    "max": [
        {"id": "llama-3.1-8b-instant",         "name": "LLaMA 3.1 8B",    "desc": "Fast & capable"},
        {"id": "mixtral-8x7b-32768",            "name": "Mixtral 8x7B",    "desc": "Great for long context"},
        {"id": "llama-3.3-70b-versatile",       "name": "LLaMA 3.3 70B",   "desc": "Most powerful"},
        {"id": "deepseek-r1-distill-llama-70b", "name": "DeepSeek R1 70B", "desc": "Advanced reasoning"},
    ],
}

# ── DATABASE ──────────────────────────────────────────────────────────────────
DB_PATH = BASE_DIR / "sai.db"

def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db

def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            email                 TEXT UNIQUE NOT NULL,
            password_hash         TEXT NOT NULL,
            tier                  TEXT DEFAULT 'free',
            display_name          TEXT,
            stripe_customer_id    TEXT,
            stripe_subscription_id TEXT,
            email_notifications   INTEGER DEFAULT 1,
            created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id         TEXT PRIMARY KEY,
            user_id    INTEGER NOT NULL,
            title      TEXT,
            model      TEXT,
            persona_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS connected_services (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            service       TEXT NOT NULL,
            access_token  TEXT,
            refresh_token TEXT,
            service_user  TEXT,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, service),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS daily_usage (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date    TEXT NOT NULL,
            count   INTEGER DEFAULT 0,
            UNIQUE(user_id, date),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS personas (
            id            TEXT PRIMARY KEY,
            user_id       INTEGER NOT NULL,
            name          TEXT NOT NULL,
            description   TEXT,
            system_prompt TEXT NOT NULL,
            avatar        TEXT DEFAULT '🤖',
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
    """)
    # Seed admin account
    db.execute(
        "INSERT OR IGNORE INTO users(email,password_hash,tier,display_name) VALUES(?,?,?,?)",
        (ADMIN_EMAIL, _hash(ADMIN_PASSWORD), "max", ADMIN_NAME)
    )
    db.commit()
    db.close()
    print(f"[SAI] Database ready at {DB_PATH}")

# ── HELPERS ───────────────────────────────────────────────────────────────────
def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def _today() -> str:
    return date.today().isoformat()

def get_usage(user_id: int) -> int:
    db = get_db()
    row = db.execute(
        "SELECT count FROM daily_usage WHERE user_id=? AND date=?", (user_id, _today())
    ).fetchone()
    db.close()
    return row["count"] if row else 0

def increment_usage(user_id: int):
    db = get_db()
    db.execute(
        "INSERT INTO daily_usage(user_id,date,count) VALUES(?,?,1) "
        "ON CONFLICT(user_id,date) DO UPDATE SET count=count+1",
        (user_id, _today())
    )
    db.commit()
    db.close()

def send_email(to: str, subject: str, html: str) -> bool:
    if not SMTP_PASS or SMTP_PASS == "YOUR_GMAIL_APP_PASSWORD":
        print(f"[SAI] Email skipped (SMTP not configured): {subject} → {to}")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        print(f"[SAI] Email sent: {subject} → {to}")
        return True
    except Exception as e:
        print(f"[SAI] Email error: {e}")
        return False

# ── AUTH DECORATORS ───────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Not authenticated"}), 401
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Not authenticated"}), 401
        user = _get_user()
        if not user or user["email"] != ADMIN_EMAIL:
            return jsonify({"error": "Forbidden"}), 403
        return f(*args, **kwargs)
    return decorated

def _get_user():
    if "user_id" not in session:
        return None
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    db.close()
    return u

# ── STATIC PAGES ──────────────────────────────────────────────────────────────
@app.route("/")
def index(): return send_from_directory(app.static_folder, "index.html")

@app.route("/login")
def login_page(): return send_from_directory(app.static_folder, "login.html")

@app.route("/pricing")
def pricing_page(): return send_from_directory(app.static_folder, "pricing.html")

@app.route("/admin")
def admin_page(): return send_from_directory(app.static_folder, "admin.html")

# ── AUTH API ──────────────────────────────────────────────────────────────────
@app.route("/api/register", methods=["POST"])
def register():
    d = request.json or {}
    email = d.get("email", "").strip().lower()
    password = d.get("password", "")
    display_name = d.get("display_name", "").strip()
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    db = get_db()
    try:
        db.execute(
            "INSERT INTO users(email,password_hash,display_name) VALUES(?,?,?)",
            (email, _hash(password), display_name or email.split("@")[0])
        )
        db.commit()
        u = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        session["user_id"] = u["id"]
        session.permanent = True
        # Welcome email (non-blocking)
        send_email(email, "Welcome to SAI! 🎉", f"""
        <div style="font-family:sans-serif;max-width:520px;margin:0 auto;padding:32px;background:#13151a;color:#e4e8f0;border-radius:16px">
            <h2 style="color:#d97757">Welcome to SAI, {display_name or email.split('@')[0]}!</h2>
            <p style="margin-top:12px;color:#9aa3b0">Your account is ready. You're on the <strong>Free plan</strong> with {FREE_MSG_LIMIT} messages per day.</p>
            <a href="{BASE_URL}/pricing" style="display:inline-block;margin-top:20px;background:#d97757;color:#fff;padding:11px 22px;border-radius:9px;text-decoration:none;font-weight:600">Upgrade to Pro →</a>
        </div>""")
        return jsonify({"success": True, "tier": "free"})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already registered"}), 409
    finally:
        db.close()

@app.route("/api/login", methods=["POST"])
def login():
    d = request.json or {}
    email = d.get("email", "").strip().lower()
    password = d.get("password", "")
    db = get_db()
    u = db.execute(
        "SELECT * FROM users WHERE email=? AND password_hash=?",
        (email, _hash(password))
    ).fetchone()
    db.close()
    if not u:
        return jsonify({"error": "Invalid email or password"}), 401
    session["user_id"] = u["id"]
    session.permanent = True
    return jsonify({"success": True, "tier": u["tier"]})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})

@app.route("/api/me")
def me():
    u = _get_user()
    if not u:
        return jsonify({"authenticated": False})
    db = get_db()
    services = db.execute(
        "SELECT service,service_user FROM connected_services WHERE user_id=?", (u["id"],)
    ).fetchall()
    db.close()
    usage = get_usage(u["id"])
    return jsonify({
        "authenticated": True,
        "id": u["id"],
        "email": u["email"],
        "display_name": u["display_name"] or u["email"].split("@")[0],
        "tier": u["tier"],
        "usage": usage,
        "limit": FREE_MSG_LIMIT if u["tier"] == "free" else None,
        "connected_services": [dict(s) for s in services],
        "stripe_pub_key": STRIPE_PUB_KEY,
        "is_admin": u["email"] == ADMIN_EMAIL,
        "email_notifications": bool(u["email_notifications"]),
    })

@app.route("/api/me/profile", methods=["POST"])
@login_required
def update_profile():
    d = request.json or {}
    db = get_db()
    if name := d.get("display_name", "").strip():
        db.execute("UPDATE users SET display_name=? WHERE id=?", (name, session["user_id"]))
    if pw := d.get("new_password", ""):
        if len(pw) < 6:
            db.close()
            return jsonify({"error": "Password too short"}), 400
        db.execute("UPDATE users SET password_hash=? WHERE id=?", (_hash(pw), session["user_id"]))
    if (notif := d.get("email_notifications")) is not None:
        db.execute("UPDATE users SET email_notifications=? WHERE id=?", (1 if notif else 0, session["user_id"]))
    db.commit()
    db.close()
    return jsonify({"success": True})

# ── MODELS API ────────────────────────────────────────────────────────────────
@app.route("/api/models")
@login_required
def get_models():
    u = _get_user()
    return jsonify(TIER_MODELS.get(u["tier"], TIER_MODELS["free"]))

# ── PERSONAS API ──────────────────────────────────────────────────────────────
BUILTIN_PERSONAS = [
    {"id": "default",  "name": "SAI",          "avatar": "🤖", "description": "Helpful & concise",   "system_prompt": "You are SAI, a helpful and concise AI assistant.",                                                                          "builtin": True},
    {"id": "coder",    "name": "Code Expert",  "avatar": "💻", "description": "Expert programmer",    "system_prompt": "You are an expert programmer. Provide clean, working code with brief explanations. Use best practices and modern syntax.",     "builtin": True},
    {"id": "writer",   "name": "Writer",        "avatar": "✍️", "description": "Creative writing",    "system_prompt": "You are a creative writing expert. Help craft engaging stories, essays, and content. Be imaginative and use vivid language.",  "builtin": True},
    {"id": "tutor",    "name": "Tutor",         "avatar": "📚", "description": "Patient teacher",     "system_prompt": "You are a patient, encouraging tutor. Break down complex topics with clear examples and analogies. Check understanding often.", "builtin": True},
    {"id": "analyst",  "name": "Analyst",       "avatar": "📊", "description": "Data & insights",     "system_prompt": "You are a data analyst. Help with analysis, statistics, and insights. Be precise, methodical, and data-driven.",               "builtin": True},
    {"id": "chef",     "name": "Chef",          "avatar": "👨‍🍳", "description": "Cooking expert",   "system_prompt": "You are a professional chef. Help with recipes, techniques, substitutions, and cooking tips. Be practical and enthusiastic.",    "builtin": True},
]

@app.route("/api/personas")
@login_required
def get_personas():
    u = _get_user()
    db = get_db()
    custom = db.execute("SELECT * FROM personas WHERE user_id=? ORDER BY created_at", (u["id"],)).fetchall()
    db.close()
    return jsonify(BUILTIN_PERSONAS + [dict(p) | {"builtin": False} for p in custom])

@app.route("/api/personas", methods=["POST"])
@login_required
def create_persona():
    u = _get_user()
    d = request.json or {}
    name = d.get("name", "").strip()
    prompt = d.get("system_prompt", "").strip()
    if not name or not prompt:
        return jsonify({"error": "Name and system prompt required"}), 400
    pid = "p_" + secrets.token_hex(6)
    db = get_db()
    db.execute(
        "INSERT INTO personas(id,user_id,name,description,system_prompt,avatar) VALUES(?,?,?,?,?,?)",
        (pid, u["id"], name, d.get("description", ""), prompt, d.get("avatar", "🤖"))
    )
    db.commit()
    db.close()
    return jsonify({"success": True, "id": pid})

@app.route("/api/personas/<pid>", methods=["DELETE"])
@login_required
def delete_persona(pid):
    db = get_db()
    db.execute("DELETE FROM personas WHERE id=? AND user_id=?", (pid, session["user_id"]))
    db.commit()
    db.close()
    return jsonify({"success": True})

# ── CHAT API ──────────────────────────────────────────────────────────────────
@app.route("/api/chat", methods=["POST"])
@login_required
def chat():
    u = _get_user()
    d = request.json or {}
    session_id    = d.get("session_id") or "sess_" + secrets.token_hex(8)
    user_message  = d.get("message", "").strip()
    model         = d.get("model", "llama-3.1-8b-instant")
    system_prompt = d.get("system_prompt", "You are SAI, a helpful and concise AI assistant.")
    temperature   = float(d.get("temperature", 0.7))
    max_tokens    = int(d.get("max_tokens", 1024))
    file_data     = d.get("file_data")
    file_name     = d.get("file_name", "file")
    file_type     = d.get("file_type", "")

    if not user_message and not file_data:
        return jsonify({"error": "Empty message"}), 400

    # Model access check
    allowed = [m["id"] for m in TIER_MODELS.get(u["tier"], [])]
    if model not in allowed:
        return jsonify({"error": f'Model not available on your {u["tier"]} plan. Please upgrade.'}), 403

    # Daily limit check
    if u["tier"] == "free" and get_usage(u["id"]) >= FREE_MSG_LIMIT:
        return jsonify({"error": f"Daily limit of {FREE_MSG_LIMIT} messages reached. Upgrade to Pro for unlimited."}), 429

    db = get_db()
    # Session management
    existing = db.execute(
        "SELECT id FROM chat_sessions WHERE id=? AND user_id=?", (session_id, u["id"])
    ).fetchone()
    if not existing:
        title = (user_message or file_name)[:45] + ("…" if len(user_message) > 45 else "")
        db.execute(
            "INSERT INTO chat_sessions(id,user_id,title,model) VALUES(?,?,?,?)",
            (session_id, u["id"], title, model)
        )
    else:
        db.execute(
            "UPDATE chat_sessions SET updated_at=CURRENT_TIMESTAMP, model=? WHERE id=?",
            (model, session_id)
        )
    db.commit()

    # Build message history
    history = db.execute(
        "SELECT role,content FROM messages WHERE session_id=? ORDER BY created_at", (session_id,)
    ).fetchall()
    groq_messages = [{"role": "system", "content": system_prompt}]
    groq_messages += [{"role": r["role"], "content": r["content"]} for r in history]

    # Handle file attachment
    display_message = user_message
    actual_model = model
    if file_data and file_type.startswith("image/"):
        groq_messages.append({
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{file_type};base64,{file_data}"}},
                {"type": "text", "text": user_message or "What's in this image?"}
            ]
        })
        actual_model = "llama-3.2-11b-vision-preview"
        display_message = f"[Image: {file_name}]\n{user_message}".strip()
    elif file_data:
        try:
            file_text = base64.b64decode(file_data).decode("utf-8", errors="ignore")[:8000]
        except Exception:
            file_text = ""
        groq_messages.append({
            "role": "user",
            "content": f"File: {file_name}\n\n{file_text}\n\n{user_message}".strip()
        })
        display_message = f"[File: {file_name}]\n{user_message}".strip()
    else:
        groq_messages.append({"role": "user", "content": user_message})

    # Save user message
    db.execute(
        "INSERT INTO messages(session_id,role,content) VALUES(?,?,?)",
        (session_id, "user", display_message)
    )
    db.commit()

    # Call Groq
    try:
        client = Groq(api_key=GROQ_API_KEY)
        resp = client.chat.completions.create(
            model=actual_model,
            messages=groq_messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        reply = resp.choices[0].message.content
    except Exception as e:
        traceback.print_exc()
        db.close()
        return jsonify({"error": f"AI error: {str(e)}"}), 500

    # Save reply
    db.execute(
        "INSERT INTO messages(session_id,role,content) VALUES(?,?,?)",
        (session_id, "assistant", reply)
    )
    db.commit()
    db.close()
    increment_usage(u["id"])
    return jsonify({"reply": reply, "session_id": session_id})

# ── VOICE TRANSCRIPTION ───────────────────────────────────────────────────────
@app.route("/api/transcribe", methods=["POST"])
@login_required
def transcribe():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file"}), 400
    audio = request.files["audio"]
    try:
        client = Groq(api_key=GROQ_API_KEY)
        result = client.audio.transcriptions.create(
            file=(audio.filename or "audio.webm", audio.read()),
            model="whisper-large-v3"
        )
        return jsonify({"text": result.text})
    except Exception as e:
        return jsonify({"error": f"Transcription failed: {str(e)}"}), 500

# ── IMAGE GENERATION ──────────────────────────────────────────────────────────
@app.route("/api/generate-image", methods=["POST"])
@login_required
def generate_image():
    u = _get_user()
    if u["tier"] == "free":
        return jsonify({"error": "Image generation requires Pro or Max plan."}), 403
    if not FAL_API_KEY or FAL_API_KEY == "YOUR_FAL_API_KEY":
        return jsonify({"error": "Image generation not configured. Add FAL_API_KEY to app.py."}), 503
    prompt = (request.json or {}).get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "Prompt required"}), 400
    try:
        res = http_requests.post(
            "https://fal.run/fal-ai/flux/schnell",
            headers={"Authorization": f"Key {FAL_API_KEY}", "Content-Type": "application/json"},
            json={"prompt": prompt, "num_images": 1, "image_size": "square_hd"},
            timeout=60
        )
        result = res.json()
        if "images" not in result:
            return jsonify({"error": "Generation failed: " + str(result)}), 500
        return jsonify({"image_url": result["images"][0]["url"]})
    except Exception as e:
        return jsonify({"error": f"Image generation error: {str(e)}"}), 500

# ── SESSIONS API ──────────────────────────────────────────────────────────────
@app.route("/api/sessions")
@login_required
def get_sessions():
    u = _get_user()
    db = get_db()
    rows = db.execute(
        "SELECT id,title,model,created_at,updated_at FROM chat_sessions WHERE user_id=? ORDER BY updated_at DESC",
        (u["id"],)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/session/<sid>")
@login_required
def get_session(sid):
    u = _get_user()
    db = get_db()
    sess = db.execute(
        "SELECT * FROM chat_sessions WHERE id=? AND user_id=?", (sid, u["id"])
    ).fetchone()
    if not sess:
        db.close()
        return jsonify({"error": "Not found"}), 404
    msgs = db.execute(
        "SELECT role,content,created_at FROM messages WHERE session_id=? ORDER BY created_at", (sid,)
    ).fetchall()
    db.close()
    return jsonify({"session": dict(sess), "messages": [dict(m) for m in msgs]})

@app.route("/api/session/<sid>", methods=["PATCH"])
@login_required
def rename_session(sid):
    u = _get_user()
    title = (request.json or {}).get("title", "").strip()
    if not title:
        return jsonify({"error": "Title required"}), 400
    db = get_db()
    db.execute("UPDATE chat_sessions SET title=? WHERE id=? AND user_id=?", (title, sid, u["id"]))
    db.commit()
    db.close()
    return jsonify({"success": True})

@app.route("/api/session/<sid>", methods=["DELETE"])
@login_required
def delete_session(sid):
    u = _get_user()
    db = get_db()
    db.execute("DELETE FROM messages WHERE session_id=?", (sid,))
    db.execute("DELETE FROM chat_sessions WHERE id=? AND user_id=?", (sid, u["id"]))
    db.commit()
    db.close()
    return jsonify({"success": True})

@app.route("/api/sessions/clear", methods=["DELETE"])
@login_required
def clear_sessions():
    u = _get_user()
    db = get_db()
    sids = [r["id"] for r in db.execute("SELECT id FROM chat_sessions WHERE user_id=?", (u["id"],)).fetchall()]
    for sid in sids:
        db.execute("DELETE FROM messages WHERE session_id=?", (sid,))
    db.execute("DELETE FROM chat_sessions WHERE user_id=?", (u["id"],))
    db.commit()
    db.close()
    return jsonify({"success": True})

@app.route("/api/session/<sid>/export")
@login_required
def export_session(sid):
    u = _get_user()
    fmt = request.args.get("format", "txt")
    db = get_db()
    sess = db.execute("SELECT * FROM chat_sessions WHERE id=? AND user_id=?", (sid, u["id"])).fetchone()
    if not sess:
        db.close()
        return jsonify({"error": "Not found"}), 404
    msgs = db.execute(
        "SELECT role,content,created_at FROM messages WHERE session_id=? ORDER BY created_at", (sid,)
    ).fetchall()
    db.close()
    title = sess["title"] or "chat"
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_")[:40]

    if fmt == "json":
        data = {"title": title, "messages": [dict(m) for m in msgs]}
        return Response(
            json.dumps(data, indent=2, ensure_ascii=False),
            mimetype="application/json",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.json"'}
        )
    elif fmt == "md":
        lines = [f"# {title}\n"]
        for m in msgs:
            label = "**You**" if m["role"] == "user" else "**SAI**"
            lines.append(f"{label}: {m['content']}\n")
        return Response(
            "\n".join(lines),
            mimetype="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.md"'}
        )
    else:
        lines = [f"Chat: {title}", "=" * 50, ""]
        for m in msgs:
            label = "You" if m["role"] == "user" else "SAI"
            lines.append(f"{label}: {m['content']}\n")
        return Response(
            "\n".join(lines),
            mimetype="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.txt"'}
        )

# ── STRIPE ────────────────────────────────────────────────────────────────────
@app.route("/api/stripe/checkout", methods=["POST"])
@login_required
def create_checkout():
    u = _get_user()
    tier = (request.json or {}).get("tier", "pro")
    price_id = STRIPE_PRO_PRICE_ID if tier == "pro" else STRIPE_MAX_PRICE_ID
    db = get_db()
    row = db.execute("SELECT stripe_customer_id FROM users WHERE id=?", (u["id"],)).fetchone()
    db.close()
    customer_id = row["stripe_customer_id"] if row and row["stripe_customer_id"] else None
    if not customer_id:
        c = stripe.Customer.create(email=u["email"])
        customer_id = c.id
        db = get_db()
        db.execute("UPDATE users SET stripe_customer_id=? WHERE id=?", (customer_id, u["id"]))
        db.commit()
        db.close()
    checkout = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=BASE_URL + "/?upgraded=1",
        cancel_url=BASE_URL + "/pricing",
    )
    return jsonify({"url": checkout.url})

@app.route("/api/stripe/portal", methods=["POST"])
@login_required
def billing_portal():
    u = _get_user()
    db = get_db()
    row = db.execute("SELECT stripe_customer_id FROM users WHERE id=?", (u["id"],)).fetchone()
    db.close()
    if not row or not row["stripe_customer_id"]:
        return jsonify({"error": "No billing account found"}), 400
    portal = stripe.billing_portal.Session.create(
        customer=row["stripe_customer_id"],
        return_url=BASE_URL + "/"
    )
    return jsonify({"url": portal.url})

@app.route("/api/stripe/webhook", methods=["POST"])
def stripe_webhook():
    try:
        event = stripe.Webhook.construct_event(
            request.data, request.headers.get("Stripe-Signature", ""), STRIPE_WEBHOOK_SECRET
        )
    except Exception:
        return "", 400

    if event["type"] in ("customer.subscription.updated", "customer.subscription.created"):
        sub = event["data"]["object"]
        if sub["status"] == "active":
            price_id = sub["items"]["data"][0]["price"]["id"]
            tier = "pro" if price_id == STRIPE_PRO_PRICE_ID else "max"
            db = get_db()
            db.execute(
                "UPDATE users SET tier=?, stripe_subscription_id=? WHERE stripe_customer_id=?",
                (tier, sub["id"], sub["customer"])
            )
            db.commit()
            u = db.execute("SELECT * FROM users WHERE stripe_customer_id=?", (sub["customer"],)).fetchone()
            db.close()
            if u and u["email_notifications"]:
                send_email(u["email"], f"You're on SAI {tier.capitalize()}! 🎉", f"""
                <div style="font-family:sans-serif;max-width:520px;margin:0 auto;padding:32px;background:#13151a;color:#e4e8f0;border-radius:16px">
                    <h2 style="color:#d97757">You're on SAI {tier.capitalize()}!</h2>
                    <p style="margin-top:12px;color:#9aa3b0">Your subscription is active. Enjoy unlimited messages and premium models.</p>
                    <a href="{BASE_URL}" style="display:inline-block;margin-top:20px;background:#d97757;color:#fff;padding:11px 22px;border-radius:9px;text-decoration:none;font-weight:600">Open SAI →</a>
                </div>""")
    elif event["type"] == "customer.subscription.deleted":
        db = get_db()
        db.execute(
            "UPDATE users SET tier='free', stripe_subscription_id=NULL WHERE stripe_customer_id=?",
            (event["data"]["object"]["customer"],)
        )
        db.commit()
        db.close()
    return "", 200

# ── OAUTH ─────────────────────────────────────────────────────────────────────
def _save_service(service, token, service_user, refresh=""):
    db = get_db()
    db.execute(
        "INSERT INTO connected_services(user_id,service,access_token,refresh_token,service_user) VALUES(?,?,?,?,?) "
        "ON CONFLICT(user_id,service) DO UPDATE SET access_token=excluded.access_token,refresh_token=excluded.refresh_token,service_user=excluded.service_user",
        (session["user_id"], service, token, refresh, service_user)
    )
    db.commit()
    db.close()

@app.route("/api/oauth/github")
@login_required
def oauth_github():
    state = secrets.token_hex(16)
    session["oauth_state"] = state
    return redirect(
        f"https://github.com/login/oauth/authorize?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={BASE_URL}/api/oauth/github/callback&scope=read:user,repo&state={state}"
    )

@app.route("/api/oauth/github/callback")
def github_callback():
    if request.args.get("state") != session.get("oauth_state"):
        return redirect("/?error=oauth_state")
    code = request.args.get("code")
    res = http_requests.post("https://github.com/login/oauth/access_token",
        data={"client_id": GITHUB_CLIENT_ID, "client_secret": GITHUB_CLIENT_SECRET, "code": code},
        headers={"Accept": "application/json"}).json()
    token = res.get("access_token")
    if not token: return redirect("/?error=github_token")
    info = http_requests.get("https://api.github.com/user", headers={"Authorization": f"token {token}"}).json()
    _save_service("github", token, info.get("login", ""))
    return redirect("/?connected=github")

@app.route("/api/oauth/discord")
@login_required
def oauth_discord():
    state = secrets.token_hex(16)
    session["oauth_state"] = state
    return redirect(
        f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={BASE_URL}/api/oauth/discord/callback&response_type=code&scope=identify+email&state={state}"
    )

@app.route("/api/oauth/discord/callback")
def discord_callback():
    code = request.args.get("code")
    res = http_requests.post("https://discord.com/api/oauth2/token", headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"client_id": DISCORD_CLIENT_ID, "client_secret": DISCORD_CLIENT_SECRET,
              "grant_type": "authorization_code", "code": code,
              "redirect_uri": f"{BASE_URL}/api/oauth/discord/callback"}).json()
    token = res.get("access_token")
    if not token: return redirect("/?error=discord_token")
    info = http_requests.get("https://discord.com/api/users/@me", headers={"Authorization": f"Bearer {token}"}).json()
    _save_service("discord", token, info.get("username", ""))
    return redirect("/?connected=discord")

@app.route("/api/oauth/google")
@login_required
def oauth_google():
    state = secrets.token_hex(16)
    session["oauth_state"] = state
    return redirect(
        f"https://accounts.google.com/o/oauth2/v2/auth?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={BASE_URL}/api/oauth/google/callback&response_type=code"
        f"&scope=https://www.googleapis.com/auth/gmail.readonly+https://www.googleapis.com/auth/userinfo.email"
        f"&access_type=offline&state={state}"
    )

@app.route("/api/oauth/google/callback")
def google_callback():
    code = request.args.get("code")
    res = http_requests.post("https://oauth2.googleapis.com/token",
        data={"client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET,
              "code": code, "grant_type": "authorization_code",
              "redirect_uri": f"{BASE_URL}/api/oauth/google/callback"}).json()
    token = res.get("access_token")
    if not token: return redirect("/?error=google_token")
    info = http_requests.get("https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {token}"}).json()
    _save_service("gmail", token, info.get("email", ""), res.get("refresh_token", ""))
    return redirect("/?connected=gmail")

@app.route("/api/disconnect/<service>", methods=["DELETE"])
@login_required
def disconnect_service(service):
    db = get_db()
    db.execute("DELETE FROM connected_services WHERE user_id=? AND service=?", (session["user_id"], service))
    db.commit()
    db.close()
    return jsonify({"success": True})

# ── ADMIN API ─────────────────────────────────────────────────────────────────
@app.route("/api/admin/users")
@admin_required
def admin_get_users():
    today = _today()
    db = get_db()
    users = db.execute(
        "SELECT id,email,display_name,tier,created_at,stripe_customer_id FROM users ORDER BY created_at DESC"
    ).fetchall()
    result = []
    for u in users:
        usage = db.execute("SELECT count FROM daily_usage WHERE user_id=? AND date=?", (u["id"], today)).fetchone()
        total = db.execute(
            "SELECT COUNT(*) as c FROM messages WHERE session_id IN (SELECT id FROM chat_sessions WHERE user_id=?)",
            (u["id"],)
        ).fetchone()
        result.append({
            "id": u["id"], "email": u["email"], "display_name": u["display_name"],
            "tier": u["tier"], "created_at": u["created_at"],
            "messages_today": usage["count"] if usage else 0,
            "total_messages": total["c"] if total else 0,
            "has_stripe": bool(u["stripe_customer_id"]),
        })
    stats = {
        "total": len(result),
        "free":  sum(1 for u in result if u["tier"] == "free"),
        "pro":   sum(1 for u in result if u["tier"] == "pro"),
        "max":   sum(1 for u in result if u["tier"] == "max"),
        "total_messages_today": sum(u["messages_today"] for u in result),
    }
    db.close()
    return jsonify({"users": result, "stats": stats})

@app.route("/api/admin/users", methods=["POST"])
@admin_required
def admin_add_user():
    d = request.json or {}
    email = d.get("email", "").strip().lower()
    password = d.get("password", "")
    tier = d.get("tier", "free")
    name = d.get("display_name", "").strip()
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password too short"}), 400
    db = get_db()
    try:
        db.execute(
            "INSERT INTO users(email,password_hash,tier,display_name) VALUES(?,?,?,?)",
            (email, _hash(password), tier, name or email.split("@")[0])
        )
        db.commit()
        return jsonify({"success": True})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already exists"}), 409
    finally:
        db.close()

@app.route("/api/admin/users/<int:uid>/tier", methods=["POST"])
@admin_required
def admin_change_tier(uid):
    tier = (request.json or {}).get("tier", "free")
    if tier not in ("free", "pro", "max"):
        return jsonify({"error": "Invalid tier"}), 400
    db = get_db()
    db.execute("UPDATE users SET tier=? WHERE id=?", (tier, uid))
    db.commit()
    db.close()
    return jsonify({"success": True})

@app.route("/api/admin/users/<int:uid>", methods=["DELETE"])
@admin_required
def admin_delete_user(uid):
    if uid == session.get("user_id"):
        return jsonify({"error": "Cannot delete your own account"}), 400
    db = get_db()
    # CASCADE handles messages/sessions/etc via FK
    db.execute("DELETE FROM users WHERE id=?", (uid,))
    db.commit()
    db.close()
    return jsonify({"success": True})

@app.route("/api/admin/email", methods=["POST"])
@admin_required
def admin_broadcast():
    d = request.json or {}
    subject = d.get("subject", "").strip()
    body = d.get("body", "").strip()
    target = d.get("target", "all")
    if not subject or not body:
        return jsonify({"error": "Subject and body required"}), 400
    db = get_db()
    if target == "all":
        users = db.execute("SELECT email FROM users WHERE email_notifications=1").fetchall()
    else:
        users = db.execute("SELECT email FROM users WHERE tier=? AND email_notifications=1", (target,)).fetchall()
    db.close()
    sent = sum(1 for u in users if send_email(u["email"], subject,
        f'<div style="font-family:sans-serif;max-width:520px;margin:0 auto;padding:32px;background:#13151a;color:#e4e8f0;border-radius:16px">{body}</div>'))
    return jsonify({"success": True, "sent": sent})

# ── STARTUP ───────────────────────────────────────────────────────────────────
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"""
╔══════════════════════════════════════╗
║           SAI is running!            ║
║  Local:  http://localhost:{port}       ║
║  Admin:  http://localhost:{port}/admin ║
╚══════════════════════════════════════╝
    """)
    app.run(debug=False, port=port, host="0.0.0.0")
