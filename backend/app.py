# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, join_room as socket_join_room, emit

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# Initialize CORS and SocketIO
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*")

# Global storage for players
players = {}

rooms = {}

def create_room(name):
    code = "1234"
    rooms[code] = {
        "players": [{"name": name, "emoji": "😀"}],
        "chat": []
    }
    return code


def join_room(code, name):
    if code not in rooms:
        return False

    rooms[code]["players"].append({
        "name": name,
        "emoji": "😀"
    })

    return True


def get_room(code):
    return rooms.get(code)


def add_chat_message(code, name, message):
    if code not in rooms:
        return

    rooms[code]["chat"].append({
        "name": name,
        "message": message
    })

# --- HELPER FUNCTIONS ---
# Note: You'll need to define these (create_room, join_room, get_room, add_chat_message) 
# or import them for the routes below to work without errors.

# --- HTTP ROUTES ---

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/create_room", methods=["POST", "OPTIONS"])
def create_room_route():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json
    name = data.get("name")
    code = create_room(name)

    return jsonify({
        "room_code": code,
        "success": True
    })

@app.route("/join_room", methods=["POST", "OPTIONS"])
def join_room_route():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json
    success = join_room(
        data.get("code"),
        data.get("name")
    )

    return jsonify({
        "success": success,
        "room": get_room(data.get("code"))
    })

@app.route("/room/<code>")
def room_info(code):
    return jsonify(get_room(code))

@app.route("/change_emoji", methods=["POST"])
def change_emoji_route():
    data = request.json
    code = data.get("code")
    name = data.get("name")
    emoji = data.get("emoji")

    room = get_room(code)
    if not room:
        return jsonify({"success": False})

    for p in room["players"]:
        if p["emoji"] == emoji:
            return jsonify({
                "success": False,
                "message": "Already taken!"
            })

    for p in room["players"]:
        if p["name"] == name:
            p["emoji"] = emoji

    return jsonify({"success": True})

@app.route("/send_chat", methods=["POST"])
def send_chat():
    data = request.json
    add_chat_message(
        data.get("code"),
        data.get("name"),
        data.get("message")
    )
    return jsonify({"success": True})

@app.route("/room_page")
def room_page():
    return render_template("room.html")

@app.route("/game_page")
def game_page():
    return render_template("game.html")

# --- SOCKET.IO EVENTS ---

@socketio.on("join_game")
def join_game(data):

    code = data.get("code")
    name = data.get("name")

    socket_join_room(code)

    players[request.sid] = {
        "code": code,
        "name": name,
        "x": 100,
        "y": 100
    }

    # Send existing players to the new player
    for sid, p in players.items():
        if sid != request.sid and p["code"] == code:
            emit("player_joined_game", {
                "id": sid,
                "name": p["name"],
                "x": p["x"],
                "y": p["y"]
            })

    # Tell everyone else a new player joined
    emit("player_joined_game", {
        "id": request.sid,
        "name": name,
        "x": 100,
        "y": 100
    }, room=code)

@socketio.on("player_move")
def player_move(data):
    if request.sid not in players:
        return

    players[request.sid]["x"] = data["x"]
    players[request.sid]["y"] = data["y"]

    code = players[request.sid]["code"]

    emit("player_moved", {
        "id": request.sid,
        "x": data["x"],
        "y": data["y"]
    }, room=code, include_self=False)

@socketio.on("disconnect")
def player_disconnect():
    if request.sid not in players:
        return

    code = players[request.sid]["code"]

    emit("player_left", {
        "id": request.sid
    }, room=code)

    if request.sid in players:
        del players[request.sid]

# --- SERVER START ---

if __name__ == "__main__":
    # Use socketio.run for WebSocket support instead of app.run
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)