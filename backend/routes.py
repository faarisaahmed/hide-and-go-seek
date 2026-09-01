# -*- coding: utf-8 -*-
"""HTTP endpoints: the three pages, plus the JSON API the lobby polls."""

from flask import Blueprint, jsonify, render_template, request

import rooms
from extensions import socketio

bp = Blueprint("main", __name__)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@bp.route("/")
def home():
    return render_template("index.html")


@bp.route("/room_page")
def room_page():
    return render_template("room.html")


@bp.route("/game_page")
def game_page():
    return render_template("game.html")


# ---------------------------------------------------------------------------
# Room API
# ---------------------------------------------------------------------------

@bp.route("/create_room", methods=["POST"])
def create_room():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "Anonymous")

    code = rooms.create(name)
    return jsonify({"success": True, "room_code": code})


@bp.route("/join_room", methods=["POST"])
def join_room():
    data = request.get_json(silent=True) or {}
    code = str(data.get("code"))
    name = data.get("name")

    success = rooms.add_player(code, name)
    return jsonify({"success": success, "room": rooms.get(code)})


@bp.route("/room/<code>")
def room_info(code):
    room = rooms.get(code)
    if room is None:
        return jsonify({"success": False, "message": "Room not found"}), 404
    return jsonify(room)


@bp.route("/change_emoji", methods=["POST"])
def change_emoji():
    data = request.get_json(silent=True) or {}
    code = str(data.get("code"))
    name = data.get("name")
    emoji = data.get("emoji")

    ok, message = rooms.set_emoji(code, name, emoji)
    if not ok:
        return jsonify({"success": False, "message": message})

    # Push the new player list so every lobby updates without waiting for
    # its next poll.
    socketio.emit("player_updated", rooms.get(code), to=code)
    return jsonify({"success": True})


@bp.route("/send_chat", methods=["POST"])
def send_chat():
    data = request.get_json(silent=True) or {}
    code = str(data.get("code"))

    if not rooms.add_chat_message(code, data.get("name"), data.get("message")):
        return jsonify({"success": False, "message": "Room not found"}), 404

    return jsonify({"success": True})
