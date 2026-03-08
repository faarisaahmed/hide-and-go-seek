# -*- coding: utf-8 -*-

import uuid
import random
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, join_room as socket_join_room, emit, leave_room

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# Initialize CORS and SocketIO
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*")

# Global storage
players = {} # Keyed by request.sid
rooms = {}   # Keyed by room_code

# --- CORE LOGIC ---

def create_room(name):
    while True:
        code = str(random.randint(1000, 9999))
        if code not in rooms:
            break

    rooms[code] = {
        # Keep consistent keys: name, emoji, isHost
        "players": [{"name": name, "emoji": "😀", "isHost": True}],
        "chat": []
    }
    return code

def join_room_logic(code, name):
    code = str(code)
    if code not in rooms:
        return False

    # Standardize to lowercase for comparison to prevent "Alice" vs "alice"
    if any(p["name"].lower() == name.lower() for p in rooms[code]["players"]):
        return False

    rooms[code]["players"].append({
        "name": name,
        "emoji": "😀",
        "isHost": False
    })
    return True

# --- SOCKET.IO EVENTS ---

@socketio.on("join_game")
def on_join_game(data):
    code = str(data.get("code"))
    name = data.get("name")
    sid = request.sid

    socket_join_room(code)

    players[sid] = {
        "code": code,
        "name": name,
        "x": 100,
        "y": 100
    }

    # FIX: Use include_self=False so the new player doesn't 
    # get a "New Player" notification for themselves.
    emit("player_joined_game", {
        "id": sid,
        "name": name,
        "x": 100,
        "y": 100
    }, to=code, include_self=False)

    # Send current state of all existing players to ONLY the newcomer
    for other_sid, p in players.items():
        if other_sid != sid and p["code"] == code:
            emit("player_joined_game", {
                "id": other_sid,
                "name": p["name"],
                "x": p["x"],
                "y": p["y"]
            }, to=sid) # Specifically target the newcomer

# --- HTTP ROUTES ---

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/create_room", methods=["POST"])
def create_room_route():
    data = request.json
    name = data.get("name", "Anonymous")
    code = create_room(name)
    return jsonify({"room_code": code, "success": True})

@app.route("/join_room", methods=["POST"])
def join_room_route():
    data = request.json
    code = str(data.get("code"))
    name = data.get("name")
    
    success = join_room_logic(code, name)
    return jsonify({
        "success": success,
        "room": rooms.get(code)
    })

@app.route("/room/<code>")
def room_info(code):
    # Ensure we return a 404 structure if room doesn't exist
    room = rooms.get(str(code))
    if not room:
        return jsonify({"success": False, "message": "Room not found"}), 404
    return jsonify(room)

@app.route("/change_emoji", methods=["POST"])
def change_emoji_route():
    data = request.json
    code, name, emoji = str(data.get("code")), data.get("name"), data.get("emoji")

    room = rooms.get(code)
    if not room:
        return jsonify({"success": False})

    # Check if emoji is taken
    if any(p["emoji"] == emoji for p in room["players"]):
        return jsonify({"success": False, "message": "Emoji already taken!"})

    for p in room["players"]:
        if p["name"] == name:
            p["emoji"] = emoji
            # Optional: Emit a socket event here so everyone's UI updates instantly
            socketio.emit("player_updated", room, to=code)
            return jsonify({"success": True})
            
    return jsonify({"success": False})

@app.route("/send_chat", methods=["POST"])
def send_chat():
    data = request.json
    code = str(data.get("code"))
    if code in rooms:
        rooms[code]["chat"].append({
            "name": data.get("name"),
            "message": data.get("message")
        })
        return jsonify({"success": True})
    return jsonify({"success": False}), 404

@app.route("/room_page")
def room_page():
    return render_template("room.html")

@app.route("/game_page")
def game_page():
    return render_template("game.html")

# --- SOCKET.IO EVENTS ---

@socketio.on("join_game")
def on_join_game(data):
    code = str(data.get("code"))
    name = data.get("name")

    socket_join_room(code)

    players[request.sid] = {
        "code": code,
        "name": name,
        "x": 100,
        "y": 100
    }

    # Notify room that a player has entered the game world
    emit("player_joined_game", {
        "id": request.sid,
        "name": name,
        "x": 100,
        "y": 100
    }, to=code)

    # Send current state of all players in THIS room to the newcomer
    for sid, p in players.items():
        if sid != request.sid and p["code"] == code:
            emit("player_joined_game", {
                "id": sid,
                "name": p["name"],
                "x": p["x"],
                "y": p["y"]
            })

@socketio.on("player_move")
def on_player_move(data):
    player = players.get(request.sid)
    if not player:
        return

    player["x"] = data["x"]
    player["y"] = data["y"]

    emit("player_moved", {
        "id": request.sid,
        "x": data["x"],
        "y": data["y"]
    }, to=player["code"], include_self=False)

@socketio.on("disconnect")
def on_disconnect():
    player = players.get(request.sid)
    if not player:
        return

    code = player["code"]
    name = player["name"]

    # 1. Notify other socket clients
    emit("player_left", {"id": request.sid}, to=code)

    # 2. Clean up HTTP room data
    if code in rooms:
        rooms[code]["players"] = [p for p in rooms[code]["players"] if p["name"] != name]
        # If room is empty, delete it
        if not rooms[code]["players"]:
            del rooms[code]

    # 3. Clean up global players dict
    del players[request.sid]

@socketio.on("start_game_request")
def on_start_game(data):
    code = str(data.get("code"))
    emit("trigger_start_game", to=code)

if __name__ == "__main__":
    # debug=True is fine for dev, but use allow_unsafe_werkzeug=True if needed
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)