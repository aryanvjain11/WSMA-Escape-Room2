"""
Bank Heist Escape Room — Flask backend.

Serves the single-page game (index.html) and provides a small JSON API
that replaces the original Supabase-backed leaderboard with a local
SQLite database (leaderboard.db), created automatically on first run.

Run with:
    python app.py
then open http://localhost:5000
"""

import os
import sqlite3
import uuid
from datetime import datetime, timezone

from flask import Flask, g, jsonify, request, send_from_directory, render_template


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "leaderboard.db")

app = Flask(__name__, static_folder=None)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_db(_exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS leaderboard (
            id TEXT PRIMARY KEY,
            player_name TEXT NOT NULL,
            completion_time_seconds INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_leaderboard_time_asc "
        "ON leaderboard (completion_time_seconds ASC)"
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")



# ---------------------------------------------------------------------------
# Leaderboard API
# ---------------------------------------------------------------------------

@app.route("/api/leaderboard", methods=["GET"])
def get_leaderboard():
    """Returns the top 10 fastest times plus average time / total players,
    mirroring the two Supabase queries the React app used to make."""
    db = get_db()

    top_rows = db.execute(
        "SELECT id, player_name, completion_time_seconds, created_at "
        "FROM leaderboard ORDER BY completion_time_seconds ASC LIMIT 10"
    ).fetchall()

    all_rows = db.execute(
        "SELECT completion_time_seconds FROM leaderboard"
    ).fetchall()

    total_players = len(all_rows)
    average_time = (
        round(sum(r["completion_time_seconds"] for r in all_rows) / total_players)
        if total_players > 0
        else 0
    )

    return jsonify(
        {
            "top": [dict(r) for r in top_rows],
            "average_time": average_time,
            "total_players": total_players,
        }
    )


@app.route("/api/leaderboard", methods=["POST"])
def post_leaderboard():
    """Insert a new completion time, then return the fresh top 10 —
    mirroring the original insert-then-select-top-10 flow."""
    payload = request.get_json(silent=True) or {}
    player_name = str(payload.get("player_name", "")).strip()
    completion_time_seconds = payload.get("completion_time_seconds")

    if not player_name:
        return jsonify({"error": "player_name is required"}), 400
    try:
        completion_time_seconds = int(completion_time_seconds)
    except (TypeError, ValueError):
        return jsonify({"error": "completion_time_seconds must be an integer"}), 400

    player_name = player_name[:30]

    db = get_db()
    entry_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    db.execute(
        "INSERT INTO leaderboard (id, player_name, completion_time_seconds, created_at) "
        "VALUES (?, ?, ?, ?)",
        (entry_id, player_name, completion_time_seconds, created_at),
    )
    db.commit()

    top_rows = db.execute(
        "SELECT id, player_name, completion_time_seconds, created_at "
        "FROM leaderboard ORDER BY completion_time_seconds ASC LIMIT 10"
    ).fetchall()

    return jsonify({"top": [dict(r) for r in top_rows]})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
else:
    # also ensure DB exists when imported by a WSGI server
    init_db()
