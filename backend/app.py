# -*- coding: utf-8 -*-
"""Application entrypoint.

Builds the Flask app, attaches CORS and Socket.IO, and wires up the HTTP
routes (``routes.py``) and socket handlers (``events.py``). The actual game
state lives in ``rooms.py``.
"""

from flask import Flask
from flask_cors import CORS

import config
from extensions import socketio


def create_app():
    app = Flask(__name__)

    # Emoji in JSON responses should stay as emoji, not \uXXXX escapes.
    app.json.ensure_ascii = False

    # Wide open on purpose: players reach the server by its LAN IP, which
    # differs per network, so there is no fixed origin to allow.
    CORS(app, resources={r"/*": {"origins": "*"}})
    socketio.init_app(app, cors_allowed_origins="*")

    from routes import bp
    app.register_blueprint(bp)

    # Imported for its @socketio.on side effects.
    import events  # noqa: F401

    return app


app = create_app()

if __name__ == "__main__":
    # allow_unsafe_werkzeug lets Flask-SocketIO use the built-in dev server.
    # It refuses by default because Werkzeug is not meant for production —
    # which is fine here, since this is the "run it on your laptop and
    # play over the Wi-Fi" entrypoint. Use a real WSGI server to deploy.
    socketio.run(
        app,
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
        allow_unsafe_werkzeug=True,
    )
