from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
import os
import sqlite3
from dotenv import load_dotenv
import re

# -----------------------
# Load env
# -----------------------
load_dotenv()

# -----------------------
# App setup
# -----------------------
app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

# ✅ Render-safe DB path
DB_PATH = "/tmp/chat_history.db"

# -----------------------
# API Keys
# -----------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not GOOGLE_API_KEY:
    print("⚠️ GOOGLE_API_KEY missing")

if not OPENAI_API_KEY:
    print("⚠️ OPENAI_API_KEY missing")

# -----------------------
# Models
# -----------------------
chat_flash = None
chat_pro = None
chat_openai = None

if GOOGLE_API_KEY:
    try:
        chat_flash = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=GOOGLE_API_KEY,
            temperature=0.7
        )
        chat_pro = ChatGoogleGenerativeAI(
            model="gemini-1.5-pro",
            google_api_key=GOOGLE_API_KEY,
            temperature=0.7
        )
    except Exception as e:
        print("❌ Gemini init error:", e)

if OPENAI_API_KEY:
    try:
        chat_openai = ChatOpenAI(
            model_name="gpt-3.5-turbo",
            openai_api_key=OPENAI_API_KEY,
            temperature=0.7
        )
    except Exception as e:
        print("❌ OpenAI init error:", e)

# -----------------------
# DB functions
# -----------------------
def get_db_connection():
    return sqlite3.connect(DB_PATH, timeout=10)

def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_name TEXT,
                question TEXT,
                answer TEXT
            )
        ''')
        conn.commit()
        conn.close()
        print("✅ Database initialized")
    except Exception as e:
        print("❌ DB error:", e)

# ✅ Run DB init ALWAYS (important for Render)
init_db()

# -----------------------
# Utils
# -----------------------
def clean_text(text: str):
    return re.sub(r'\*{1,3}', '', text)

# -----------------------
# Routes
# -----------------------
@app.route("/ask", methods=["POST"])
def ask():
    try:
        data = request.json
        if not data:
            return jsonify({"reply": "Invalid request"}), 400

        user_input = data.get("text", "").strip()
        session_name = data.get("session", "default")

        if not user_input:
            return jsonify({"reply": "Enter a message"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Cache check
        cursor.execute(
            "SELECT answer FROM chats WHERE question=? AND session_name=?",
            (user_input, session_name)
        )
        row = cursor.fetchone()

        if row:
            conn.close()
            return jsonify({"reply": row[0]})

        reply = None
        model_used = None

        # Try Gemini Flash
        if chat_flash:
            try:
                res = chat_flash.invoke([{"role": "user", "content": user_input}])
                reply = res.content if hasattr(res, "content") else str(res)
                model_used = "gemini-flash"
            except Exception as e:
                print("Flash error:", e)

        # Try Gemini Pro
        if not reply and chat_pro:
            try:
                res = chat_pro.invoke([{"role": "user", "content": user_input}])
                reply = res.content if hasattr(res, "content") else str(res)
                model_used = "gemini-pro"
            except Exception as e:
                print("Pro error:", e)

        # Try OpenAI
        if not reply and chat_openai:
            try:
                res = chat_openai.invoke([
                    {"role": "system", "content": "You are helpful."},
                    {"role": "user", "content": user_input}
                ])
                reply = res.content if hasattr(res, "content") else str(res)
                model_used = "openai"
            except Exception as e:
                print("OpenAI error:", e)

        if not reply:
            return jsonify({"reply": "🚫 AI failed (check API keys)"}), 500

        reply = clean_text(reply)
        final_reply = f"[{model_used}] {reply}"

        # Save
        cursor.execute(
            "INSERT INTO chats (session_name, question, answer) VALUES (?, ?, ?)",
            (session_name, user_input, final_reply)
        )
        conn.commit()
        conn.close()

        return jsonify({"reply": final_reply})

    except Exception as e:
        print("❌ /ask error:", e)
        return jsonify({"reply": str(e)}), 500


@app.route("/sessions")
def sessions():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT session_name FROM chats")
        data = [row[0] for row in cursor.fetchall()]
        conn.close()
        return jsonify({"sessions": data})
    except Exception as e:
        print("❌ sessions error:", e)
        return jsonify({"sessions": []}), 500


@app.route("/history/<session>")
def history(session):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT question, answer FROM chats WHERE session_name=?",
            (session,)
        )
        rows = cursor.fetchall()
        conn.close()

        history = []
        for q, a in rows:
            history.append({"sender": "user", "text": q})
            history.append({"sender": "bot", "text": a})

        return jsonify({"history": history})
    except Exception as e:
        print("❌ history error:", e)
        return jsonify({"history": []}), 500


# -----------------------
# Serve React
# -----------------------
@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:path>")
def static_proxy(path):
    if os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, "index.html")


# -----------------------
# LOCAL RUN ONLY
# -----------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)