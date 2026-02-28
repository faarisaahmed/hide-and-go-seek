from flask import Flask, request, jsonify
from flask_cors import CORS

from room_manager import create_room, join_room, get_room

app = Flask(__name__)

# This is the important line
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

if __name__ == "__main__":
    app.run(debug=True)