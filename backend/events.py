# -*- coding: utf-8 -*-
"""Socket.IO event handlers.

Both pages open a socket. The lobby sends ``join_lobby`` just to subscribe
to room broadcasts; the game page sends ``join_game``, which also places
the player in the world at a spawn point.

Naming note: Socket.IO rooms and game rooms line up exactly here, since
every client subscribes to the Socket.IO room named after its room code.
``flask_socketio.join_room`` is aliased to keep it distinct from our own
room helpers.
"""

from flask import request
from flask_socketio import emit
from flask_socketio import join_room as subscribe_to_room

import config
import rooms
from extensions import socketio


def _world_payload(player):
    """How a player appears to everyone else in the game world."""
    return {
        "id": player["sid"],
        "name": player["name"],
        "emoji": player["emoji"],
        "x": player["x"],
        "y": player["y"],
    }


def _reject(message):
    emit("join_rejected", {"message": message})


@socketio.on("join_lobby")
def on_join_lobby(data):
    """A lobby page is asking to receive this room's broadcasts."""
    code = rooms.clean_code(data.get("code"))
    name = data.get("name")

    if rooms.attach(request.sid, code, name) is None:
        _reject("That room has closed.")
        return

    subscribe_to_room(code)
    emit("room_updated", rooms.public_view(code))


@socketio.on("join_game")
def on_join_game(data):
    """A game page is entering the world."""
    code = rooms.clean_code(data.get("code"))
    name = data.get("name")

    player = rooms.enter_game(request.sid, code, name, config.DEFAULT_MAP)
    if player is None:
        _reject("That room has closed.")
        return

    subscribe_to_room(code)

    # Tell the newcomer where to stand, which map to load, and who is
    # already here. One message, so the client can start in one step.
    emit("game_joined", {
        "map": config.DEFAULT_MAP,
        "you": _world_payload(player),
        "players": [
            _world_payload(other)
            for other in rooms.players_in_game(code, exclude_sid=request.sid)
        ],
    })

    emit("player_joined_game", _world_payload(player),
         to=code, include_self=False)


@socketio.on("player_move")
def on_player_move(data):
    """A client reported a new position; relay it to the rest of the room."""
    if not isinstance(data, dict):
        return

    code, player = rooms.move(request.sid, data.get("x"), data.get("y"))
    if player is None:
        return

    emit("player_moved",
         {"id": request.sid, "x": player["x"], "y": player["y"]},
         to=code, include_self=False)


@socketio.on("start_game_request")
def on_start_game(data):
    """The host pressed Start Game; send the whole room to the game page."""
    player = rooms.connected_player(request.sid)
    if player is None or not player["isHost"]:
        # Only the host starts the game, whatever a client claims.
        return

    emit("trigger_start_game", to=rooms.room_code_of(request.sid))


@socketio.on("disconnect")
def on_disconnect():
    """A socket went away.

    The player is not removed: they may just be moving from the lobby to
    the game page. They stop being drawn in the world, and rooms.py drops
    them for good only if they stay gone.
    """
    code, player = rooms.detach(request.sid)
    if player is None:
        return

    emit("player_left", {"id": request.sid}, to=code)
    socketio.emit("room_updated", rooms.public_view(code), to=code)
