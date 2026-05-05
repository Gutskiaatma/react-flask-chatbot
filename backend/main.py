from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
import os
import sqlite3
from dotenv import load_dotenv
import re

# -----------------------
# Load environment
# -----------------------
load_dotenv()

# -----------------------
# App setup
# -----------------------
app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

# ✅ Use /tmp for deployment (Render/Railway safe)
DB_PATH = os.path.join("/tmp", "chat_history.db")

# -----------------------
# Check API Keys
# -----------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not GOOGLE_API_KEY:
    print("⚠️ WARNING: GOOGLE_API_KEY is missing")

if not OPENAI_API_KEY:
    print("⚠️ WARNING: OPENAI_API_KEY is missing")

# -----------------------
# Initialize models (only if keys exist)
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
# Utility functions
# -----------------------
def clean_text(text: str):
    return re.sub(r'\*{1,3}', '', text)

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
        print("❌ DB Init Error:", e)

# ✅ IMPORTANT: Run in production too
init_db()

# -----------------------
# API Routes
# -----------------------
@app.route("/ask", methods=["POST"])
def ask():
    try:
        data = request.json

        if not data:
            return jsonify({"reply": "Invalid request body"}), 400

        user_input = data.get("text", "").strip()
        session_name = data.get("session", "default")

        if not user_input:
            return jsonify({"reply": "Please enter a message."}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # -----------------------
        # Check cache
        # -----------------------
        cursor.execute(
            "SELECT answer FROM chats WHERE question = ? AND session_name = ?",
            (user_input, session_name)
        )
        row = cursor.fetchone()

        if row:
            conn.close()
            return jsonify({"reply": row[0]})

        reply = None
        used_model = None

        # -----------------------
        # Try Gemini Flash
        # -----------------------
        if chat_flash:
            try:
                response = chat_flash.invoke([{"role": "user", "content": user_input}])
                reply = response.content if hasattr(response, "content") else str(response)
                used_model = "gemini-flash"
            except Exception as e:
                print("⚠️ Gemini Flash failed:", e)

        # -----------------------
        # Try Gemini Pro
        # -----------------------
        if not reply and chat_pro:
            try:
                response = chat_pro.invoke([{"role": "user", "content": user_input}])
                reply = response.content if hasattr(response, "content") else str(response)
                used_model = "gemini-pro"
            except Exception as e:
                print("⚠️ Gemini Pro failed:", e)

        # -----------------------
        # Try OpenAI
        # -----------------------
        if not reply and chat_openai:
            try:
                response = chat_openai.invoke([
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": user_input}
                ])
                reply = response.content if hasattr(response, "content") else str(response)
                used_model = "openai-gpt3.5"
            except Exception as e:
                print("⚠️ OpenAI failed:", e)

        # -----------------------
        # If all fail
        # -----------------------
        if not reply:
            return jsonify({
                "reply": "🚫 All AI services failed. Check API keys or logs."
            }), 500

        # Clean response
        reply = clean_text(reply)
        formatted_reply = f"[{used_model}] {reply}"

        # Save to DB
        cursor.execute(
            "INSERT INTO chats (session_name, question, answer) VALUES (?, ?, ?)",
            (session_name, user_input, formatted_reply)
        )
        conn.commit()
        conn.close()

        return jsonify({"reply": formatted_reply})

    except Exception as e:
        print("❌ /ask ERROR:", e)
        return jsonify({"reply": f"Server Error: {str(e)}"}), 500


@app.route("/sessions", methods=["GET"])
def list_sessions():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT session_name FROM chats")
        sessions = [row[0] for row in cursor.fetchall()]
        conn.close()
        return jsonify({"sessions": sessions})
    except Exception as e:
        print("❌ /sessions ERROR:", e)
        return jsonify({"sessions": []}), 500


@app.route("/history/<session_name>", methods=["GET"])
def session_history(session_name):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT question, answer FROM chats WHERE session_name = ?",
            (session_name,)
        )
        rows = cursor.fetchall()
        conn.close()

        history = []
        for q, a in rows:
            history.append({"sender": "user", "text": q})
            history.append({"sender": "bot", "text": a})

        return jsonify({"history": history})
    except Exception as e:
        print("❌ /history ERROR:", e)
        return jsonify({"history": []}), 500


# -----------------------
# Serve React App
# -----------------------
@app.route("/")
def serve_react():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:path>")
def serve_static(path):
    file_path = os.path.join(app.static_folder, path)
    if os.path.exists(file_path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, "index.html")


# -----------------------
# Run
# -----------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)