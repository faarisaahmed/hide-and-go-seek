# -*- coding: utf-8 -*-
from room_manager import create_room, join_room, get_room, add_chat_message
from flask import Flask, request, jsonify
from flask_cors import CORS

from room_manager import create_room, join_room, get_room

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

CORS(app, resources={r"/*": {"origins": "*"}})

@app.route("/")
def home():
    return "Hide and Go Seek Server Running"

@app.route("/create_room", methods=["POST", "OPTIONS"])
def create_room_route():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json
    name = data.get("name")

    code = create_room(name)

    return jsonify({"room_code": code})

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

    # Check emoji uniqueness
    for p in room["players"]:
        if p["emoji"] == emoji:
            return jsonify({
                "success": False,
                "message": "Already taken!"
            })

    # Change emoji
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

if __name__ == "__main__":
    app.run(debug=True)