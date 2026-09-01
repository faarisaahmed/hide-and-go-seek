# -*- coding: utf-8 -*-
"""In-memory store for lobbies and connected players.

Two separate things are tracked here, and it helps to keep them straight:

``_rooms``
    Keyed by room code. The *lobby* view of a room: who has joined, what
    emoji they picked, and the chat log. The HTTP endpoints read and write
    this.

``_players``
    Keyed by Socket.IO session id (``sid``). Where each *connected* client
    currently is in the game world. The socket event handlers own this.

Nothing is persisted, so restarting the server clears every room.
"""

import random

import config

_rooms = {}
_players = {}


# ---------------------------------------------------------------------------
# Lobbies
# ---------------------------------------------------------------------------

def _new_room_code():
    """Return a room code that is not already in use."""
    while True:
        code = str(random.randint(config.ROOM_CODE_MIN, config.ROOM_CODE_MAX))
        if code not in _rooms:
            return code


def create(host_name):
    """Open a new room with ``host_name`` as its host. Returns the code."""
    code = _new_room_code()
    _rooms[code] = {
        "players": [_new_lobby_player(host_name, is_host=True)],
        "chat": [],
    }
    return code


def _new_lobby_player(name, is_host=False):
    return {"name": name, "emoji": config.DEFAULT_EMOJI, "isHost": is_host}


def get(code):
    """Return the room dict for ``code``, or None if there is no such room."""
    return _rooms.get(str(code))


def add_player(code, name):
    """Add ``name`` to a room's lobby.

    Returns False if the room does not exist or the name is already taken.
    Names are compared case-insensitively so "Alice" and "alice" collide.
    """
    room = get(code)
    if room is None:
        return False

    if any(p["name"].lower() == name.lower() for p in room["players"]):
        return False

    room["players"].append(_new_lobby_player(name))
    return True


def remove_player(code, name):
    """Drop ``name`` from a room, deleting the room once it is empty."""
    code = str(code)
    room = _rooms.get(code)
    if room is None:
        return

    room["players"] = [p for p in room["players"] if p["name"] != name]
    if not room["players"]:
        del _rooms[code]


def set_emoji(code, name, emoji):
    """Give ``name`` a new emoji.

    Returns ``(ok, message)``. An emoji already in use by someone else in
    the room is rejected so players stay visually distinct.
    """
    room = get(code)
    if room is None:
        return False, "Room not found"

    if any(p["emoji"] == emoji for p in room["players"]):
        return False, "Emoji already taken!"

    for player in room["players"]:
        if player["name"] == name:
            player["emoji"] = emoji
            return True, None

    return False, "Player not in room"


def add_chat_message(code, name, message):
    """Append a chat message, trimming the log to its maximum length."""
    room = get(code)
    if room is None:
        return False

    chat = room["chat"]
    chat.append({"name": name, "message": message})
    del chat[:-config.MAX_CHAT_MESSAGES]
    return True


# ---------------------------------------------------------------------------
# Connected players (game world)
# ---------------------------------------------------------------------------

def connect(sid, code, name):
    """Record that ``sid`` entered the game world, and return its state."""
    _players[sid] = {
        "code": str(code),
        "name": name,
        "x": config.SPAWN_X,
        "y": config.SPAWN_Y,
    }
    return _players[sid]


def connected(sid):
    """Return the game-world state for ``sid``, or None if not connected."""
    return _players.get(sid)


def disconnect(sid):
    """Forget ``sid`` and return the state it had, or None if unknown."""
    return _players.pop(sid, None)


def others_in_room(code, sid):
    """Yield ``(other_sid, state)`` for everyone in ``code`` except ``sid``."""
    code = str(code)
    for other_sid, player in _players.items():
        if other_sid != sid and player["code"] == code:
            yield other_sid, player


def move(sid, x, y):
    """Update where ``sid`` is. Returns its state, or None if not connected."""
    player = _players.get(sid)
    if player is None:
        return None

    player["x"] = x
    player["y"] = y
    return player
