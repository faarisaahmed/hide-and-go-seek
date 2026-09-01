# -*- coding: utf-8 -*-
"""Socket.IO event handlers.

Naming note: Socket.IO rooms and game lobbies happen to be the same thing
here — every client joins the Socket.IO room named after its room code, so
broadcasting to a lobby is just ``to=code``. ``flask_socketio.join_room``
is imported under an alias to keep it distinct from our own room helpers.
"""

from flask import request
from flask_socketio import emit
from flask_socketio import join_room as subscribe_to_room

import rooms
from extensions import socketio


def _player_payload(sid, player):
    """Shape a connected player for the wire."""
    return {
        "id": sid,
        "name": player["name"],
        "x": player["x"],
        "y": player["y"],
    }


@socketio.on("join_game")
def on_join_game(data):
    """A client entered a lobby or the game world.

    Both the lobby page and the game page emit this, which is how a player
    keeps receiving room broadcasts across the page navigation.
    """
    code = str(data.get("code"))
    sid = request.sid

    subscribe_to_room(code)
    player = rooms.connect(sid, code, data.get("name"))

    # Tell everyone already here about the newcomer. include_self=False so
    # the newcomer is not announced to itself.
    emit("player_joined_game", _player_payload(sid, player),
         to=code, include_self=False)

    # Then catch the newcomer up on everyone who was already in the world.
    for other_sid, other in rooms.others_in_room(code, sid):
        emit("player_joined_game", _player_payload(other_sid, other), to=sid)


@socketio.on("player_move")
def on_player_move(data):
    """A client reported a new position; relay it to the rest of the room."""
    player = rooms.move(request.sid, data["x"], data["y"])
    if player is None:
        return

    emit("player_moved", {"id": request.sid, "x": data["x"], "y": data["y"]},
         to=player["code"], include_self=False)


@socketio.on("start_game_request")
def on_start_game(data):
    """The host pressed Start Game; send the whole room to the game page."""
    emit("trigger_start_game", to=str(data.get("code")))


@socketio.on("disconnect")
def on_disconnect():
    """A client went away: drop it from the world and from its lobby."""
    player = rooms.disconnect(request.sid)
    if player is None:
        return

    emit("player_left", {"id": request.sid}, to=player["code"])
    rooms.remove_player(player["code"], player["name"])
