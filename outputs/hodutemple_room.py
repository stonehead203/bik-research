import json
import math
import os
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path
from uuid import UUID

from flask import Blueprint, current_app, jsonify, redirect, request, send_from_directory, session

hodutemple = Blueprint("hodutemple", __name__)
ASSETS = Path(__file__).parent / "hodutemple"
CAPACITY = 10
PRESENCE_SECONDS = 22
ASSET_NAMES = {"scene.mjs", "style.css", "room.js", "market.js", "chat.js"}
EXERCISES = {"pull", "push", "sweep"}


def member():
    if session.get("logged_in"):
        return str(session.get("username") or "")


def private(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.vary.add("Cookie")
    return response


@hodutemple.get("/hodutemple")
def enter():
    if not member():
        return private(redirect("/?hodutemple=1"))
    return private(send_from_directory(ASSETS, "index.html"))


@hodutemple.get("/hodutemple/assets/<name>")
def asset(name):
    if name not in ASSET_NAMES:
        return "", 404
    return send_from_directory(ASSETS, name, max_age=300)


def number(value, low, high):
    if type(value) in (float, int) and low <= value <= high and math.isfinite(value):
        return round(value, 3)
    raise ValueError("invalid coordinate")


def uuid(value):
    return str(UUID(str(value)))


def room_db():
    path = current_app.config.get("HODUTEMPLE_DB") or os.path.join(
        tempfile.gettempdir(), "bik-hodutemple-room-v1.sqlite3"
    )
    db = sqlite3.connect(path, timeout=2)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS members (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, state TEXT NOT NULL, seen REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
            sender TEXT NOT NULL, kind TEXT NOT NULL, message TEXT, created REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS events_sender_kind ON events(sender, kind, created);
    """)
    return db


def clean_event(data):
    if not isinstance(data, dict) or data.get("kind") not in ("speech", "pray"):
        raise ValueError("invalid event")
    kind = data["kind"]
    message = data.get("message") if kind == "speech" else None
    if kind == "speech":
        if not isinstance(message, str) or not (1 <= len(message.strip()) <= 100):
            raise ValueError("invalid speech")
        message = message.strip()
    return uuid(data.get("id")), kind, message


@hodutemple.post("/api/hodutemple/room")
def room():
    owner = member()
    if not owner:
        return private(jsonify(error="login_required")), 401
    if request.headers.get("Sec-Fetch-Site") == "cross-site":
        return private(jsonify(error="invalid_origin")), 403
    if request.content_length is None or request.content_length > 4096:
        return private(jsonify(error="invalid_size")), 400
    payload = request.get_json(silent=True)
    try:
        identity = uuid(payload["id"])
        if payload.get("leave") is True:
            with closing(room_db()) as db, db:
                db.execute("DELETE FROM members WHERE id = ? AND owner = ?", (identity, owner))
            return private(jsonify(ok=True))
        cursor = payload.get("cursor")
        if cursor is not None and (type(cursor) is not int or not 0 <= cursor < 2**53):
            raise ValueError("invalid cursor")
        events = payload.get("events", [])
        if not isinstance(events, list) or len(events) > 4:
            raise ValueError("invalid events")
        events = [clean_event(event) for event in events]
        raw = payload["state"]
        state = {
            "id": identity,
            "nickname": str(session.get("nickname") or owner)[:32],
            "x": number(raw["x"], -32, 32),
            "z": number(raw["z"], -33, 43),
            "yaw": number(raw["yaw"], -10, 10),
            "jump": number(raw.get("jump", 0), 0, 3),
            "seated": raw.get("seated") is True,
            "exercise": raw.get("exercise") if raw.get("exercise") in EXERCISES else None,
        }
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        return private(jsonify(error="invalid_state")), 400

    now = time.time()
    with closing(room_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM members WHERE seen < ?", (now - PRESENCE_SECONDS,))
        db.execute("DELETE FROM events WHERE created < ?", (now - 7,))
        existing = db.execute("SELECT owner FROM members WHERE id = ?", (identity,)).fetchone()
        if existing and existing["owner"] != owner:
            return private(jsonify(error="invalid_member")), 403
        if not existing and db.execute("SELECT COUNT(*) FROM members").fetchone()[0] >= CAPACITY:
            return private(jsonify(error="room_full")), 409
        db.execute(
            """INSERT INTO members VALUES (?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET state=excluded.state, seen=excluded.seen""",
            (identity, owner, json.dumps(state, ensure_ascii=False), now),
        )
        for event_id, kind, message in events:
            cooldown = 1 if kind == "speech" else .8
            latest = db.execute(
                "SELECT MAX(created) FROM events WHERE sender=? AND kind=?", (identity, kind)
            ).fetchone()[0]
            if latest is None or now - latest >= cooldown:
                db.execute(
                    "INSERT OR IGNORE INTO events(id,sender,kind,message,created) VALUES(?,?,?,?,?)",
                    (event_id, identity, kind, message, now),
                )
        head = db.execute("SELECT seq FROM sqlite_sequence WHERE name='events'").fetchone()
        head = head[0] if head else 0
        peers = [json.loads(row["state"]) for row in db.execute(
            "SELECT state FROM members WHERE id != ?", (identity,)
        )]
        updates = [] if cursor is None or cursor > head else [
            {"id": row["sender"], "kind": row["kind"], "message": row["message"],
             "age": round((now - row["created"]) * 1000)}
            for row in db.execute(
                "SELECT * FROM events WHERE seq > ? AND sender != ? AND created >= ? ORDER BY seq",
                (cursor, identity, now - 5),
            )
        ]
    return private(jsonify(nickname=state["nickname"], peers=peers, events=updates, cursor=head))
