# -*- coding: utf-8 -*-
"""HTTP endpoints: the three pages, plus the JSON API the lobby polls."""

from flask import Blueprint, jsonify, render_template, request

import rooms
from extensions import socketio

bp = Blueprint("main", __name__)


def _body():
    return request.get_json(silent=True) or {}


def _push_room(code):
    """Tell everyone in a room that its state changed."""
    socketio.emit("room_updated", rooms.public_view(code), to=code)


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
    name = _body().get("name")

    code = rooms.create(name)
    if code is None:
        return jsonify({"success": False, "message": "Please pick a shorter name"}), 400

    return jsonify({"success": True, "room_code": code})


@bp.route("/join_room", methods=["POST"])
def join_room():
    data = _body()
    code = data.get("code")

    ok, message = rooms.add_player(code, data.get("name"))
    if not ok:
        return jsonify({"success": False, "message": message}), 400

    _push_room(code)
    return jsonify({"success": True, "room": rooms.public_view(code)})


@bp.route("/room/<code>")
def room_info(code):
    room = rooms.public_view(code)
    if room is None:
        return jsonify({"success": False, "message": "Room not found"}), 404
    return jsonify(room)


@bp.route("/change_emoji", methods=["POST"])
def change_emoji():
    data = _body()
    code = data.get("code")

    ok, message = rooms.set_emoji(code, data.get("name"), data.get("emoji"))
    if not ok:
        return jsonify({"success": False, "message": message})

    _push_room(code)
    return jsonify({"success": True})


@bp.route("/send_chat", methods=["POST"])
def send_chat():
    data = _body()
    code = data.get("code")

    ok, message = rooms.add_chat_message(code, data.get("name"), data.get("message"))
    if not ok:
        status = 404 if message == "Room not found" else 400
        return jsonify({"success": False, "message": message}), status

    _push_room(code)
    return jsonify({"success": True})
