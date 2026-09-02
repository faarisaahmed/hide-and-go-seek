# -*- coding: utf-8 -*-
"""Room and player state.

A room holds one record per player, keyed by a normalised form of their
name. That name is the player's identity for as long as the room exists:
their socket comes and goes (navigating from the lobby to the game drops
one socket and opens another), but the record stays put.

Keeping connections as an *attribute* of a player, rather than in a
separate store, is what stops a player disappearing from the lobby the
moment the game starts.

Nothing is persisted, so restarting the server clears every room.
"""

import random
import time

import config
import maps

# code -> room. Insertion-ordered, which is how we know who joined first
# when a new host has to be picked.
_rooms = {}

# socket id -> (code, player_key), so a disconnect can find its player.
_sid_index = {}


def _key(name):
    """Identity for a name. Case and padding do not make a new player."""
    return name.strip().lower()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def clean_name(name):
    """Return a usable display name, or None if it is not acceptable."""
    if not isinstance(name, str):
        return None

    name = " ".join(name.split())  # collapse runs of whitespace
    if not name or len(name) > config.MAX_NAME_LENGTH:
        return None

    return name


def clean_code(code):
    """Return a well-formed room code, or None."""
    if not isinstance(code, (str, int)):
        return None

    code = str(code).strip()
    if len(code) != config.ROOM_CODE_LENGTH or not code.isdigit():
        return None

    return code


def clean_message(message):
    """Return a usable chat message, or None."""
    if not isinstance(message, str):
        return None

    message = message.strip()
    if not message:
        return None

    return message[:config.MAX_CHAT_LENGTH]


def _clean_coord(value):
    """Coordinates arrive from the client, so they cannot be trusted."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return float(value)


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------

def _expire(code, now=None):
    """Drop players who disconnected and never came back; tidy the room.

    Called whenever a room is looked at, which avoids needing a background
    timer. A room with nobody left in it is deleted, and a room that lost
    its host gets a new one.
    """
    room = _rooms.get(code)
    if room is None:
        return None

    now = now if now is not None else time.monotonic()
    deadline = now - config.DISCONNECT_GRACE_SECONDS

    expired = [
        key for key, player in room["players"].items()
        if player["left_at"] is not None and player["left_at"] < deadline
    ]
    for key in expired:
        del room["players"][key]

    if not room["players"]:
        del _rooms[code]
        return None

    # Whoever has been here longest takes over if the host is gone.
    if not any(p["isHost"] for p in room["players"].values()):
        next(iter(room["players"].values()))["isHost"] = True

    return room


def _expire_all():
    for code in list(_rooms):
        _expire(code)


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------

def _new_room_code():
    while True:
        code = str(random.randint(config.ROOM_CODE_MIN, config.ROOM_CODE_MAX))
        if code not in _rooms:
            return code


def _free_emoji(room):
    """First emoji nobody in the room is using, so players look distinct."""
    taken = {p["emoji"] for p in room["players"].values()}
    for emoji in config.EMOJI_POOL:
        if emoji not in taken:
            return emoji
    return random.choice(config.EMOJI_POOL)


def _new_player(room, name, is_host):
    return {
        "name": name,
        "emoji": _free_emoji(room),
        "isHost": is_host,
        "x": config.SPAWN_X,
        "y": config.SPAWN_Y,
        "sid": None,
        # When their socket dropped, or None while connected. Drives expiry.
        # Set at creation too, so a room nobody ever connects to is cleaned
        # up rather than lingering forever.
        "left_at": time.monotonic(),
        # True once they have been placed in the world. Survives a dropped
        # socket, which is what lets a reconnect resume in place.
        "in_game": False,
    }


def create(host_name):
    """Open a room with ``host_name`` as host. Returns the code, or None."""
    host_name = clean_name(host_name)
    if host_name is None:
        return None

    # Good moment to clear out rooms everyone has already abandoned.
    _expire_all()

    code = _new_room_code()
    room = {"players": {}, "chat": []}
    _rooms[code] = room
    room["players"][_key(host_name)] = _new_player(room, host_name, is_host=True)

    return code


def get(code):
    """The room for ``code`` after expiring stale players, or None."""
    code = clean_code(code)
    if code is None:
        return None
    return _expire(code)


def public_view(code):
    """What the lobby is allowed to see: player list and chat."""
    room = get(code)
    if room is None:
        return None

    return {
        "players": [
            {
                "name": p["name"],
                "emoji": p["emoji"],
                "isHost": p["isHost"],
                "connected": p["sid"] is not None,
            }
            for p in room["players"].values()
        ],
        "chat": room["chat"],
    }


def add_player(code, name):
    """Add ``name`` to a room. Returns ``(ok, message)``."""
    name = clean_name(name)
    if name is None:
        return False, "Please pick a shorter name"

    room = get(code)
    if room is None:
        return False, "Room not found"

    if _key(name) in room["players"]:
        return False, "That name is already taken in this room"

    room["players"][_key(name)] = _new_player(room, name, is_host=False)
    return True, None


def find_player(code, name):
    """The player record for ``name`` in ``code``, or None."""
    room = get(code)
    if room is None or not isinstance(name, str):
        return None
    return room["players"].get(_key(name))


def is_host(code, name):
    player = find_player(code, name)
    return bool(player and player["isHost"])


def set_emoji(code, name, emoji):
    """Give a player a new emoji. Returns ``(ok, message)``."""
    room = get(code)
    if room is None:
        return False, "Room not found"

    if emoji not in config.EMOJI_POOL:
        return False, "That is not one of the available emoji"

    player = room["players"].get(_key(name)) if isinstance(name, str) else None
    if player is None:
        return False, "You are not in this room"

    if player["emoji"] == emoji:
        return True, None  # already theirs; nothing to do

    if any(p["emoji"] == emoji for p in room["players"].values()):
        return False, "Emoji already taken!"

    player["emoji"] = emoji
    return True, None


def add_chat_message(code, name, message):
    """Append a chat message. Returns ``(ok, message)``."""
    room = get(code)
    if room is None:
        return False, "Room not found"

    player = room["players"].get(_key(name)) if isinstance(name, str) else None
    if player is None:
        return False, "You are not in this room"

    text = clean_message(message)
    if text is None:
        return False, "Message is empty"

    chat = room["chat"]
    chat.append({"name": player["name"], "message": text})
    del chat[:-config.MAX_CHAT_MESSAGES]
    return True, None


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------

def _bind(sid, code, name):
    """Point a player's record at a socket. Returns the player, or None."""
    player = find_player(code, name)
    if player is None:
        return None

    # A second tab logging in as the same player takes over the record.
    if player["sid"] is not None and player["sid"] != sid:
        _sid_index.pop(player["sid"], None)

    player["sid"] = sid
    player["left_at"] = None
    _sid_index[sid] = (clean_code(code), _key(name))

    return player


def attach(sid, code, name):
    """Bind a socket from the lobby. Returns the player, or None.

    Being in the lobby means not being in the world, so anyone who backs
    out of the game to the lobby stops being drawn and will be given a
    fresh spawn if they go back in.
    """
    player = _bind(sid, code, name)
    if player is not None:
        player["in_game"] = False
    return player


def enter_game(sid, code, name, map_name):
    """Put a player into the game world. Returns the player, or None.

    A player who is already in the world keeps the position they had, so
    a dropped connection or a refresh resumes where they were standing
    instead of teleporting them back to spawn.
    """
    player = _bind(sid, code, name)
    if player is None:
        return None

    if not player["in_game"]:
        room = _rooms[clean_code(code)]
        # Space players out using the order they entered the world.
        index = sum(1 for p in room["players"].values() if p["in_game"])
        player["x"], player["y"] = maps.spawn_point(map_name, index)
        player["in_game"] = True

    return player


def detach(sid):
    """Mark a socket's player as disconnected. Returns ``(code, player)``.

    The player is kept, so the lobby does not lose them while they are
    navigating to the game page. :func:`_expire` removes them later if
    they really did leave.
    """
    entry = _sid_index.pop(sid, None)
    if entry is None:
        return None, None

    code, key = entry
    room = _rooms.get(code)
    if room is None:
        return code, None

    player = room["players"].get(key)
    if player is None or player["sid"] != sid:
        # Superseded by a newer socket for the same player; nothing to do.
        return code, None

    player["sid"] = None
    player["left_at"] = time.monotonic()

    return code, player


def room_code_of(sid):
    """The room code a socket belongs to, or None."""
    entry = _sid_index.get(sid)
    return entry[0] if entry else None


def connected_player(sid):
    """The player behind a socket, or None."""
    entry = _sid_index.get(sid)
    if entry is None:
        return None

    code, key = entry
    room = _rooms.get(code)
    return room["players"].get(key) if room else None


def players_in_game(code, exclude_sid=None):
    """Everyone currently in the game world of a room."""
    room = get(code)
    if room is None:
        return []

    return [
        p for p in room["players"].values()
        if p["in_game"] and p["sid"] is not None and p["sid"] != exclude_sid
    ]


def move(sid, x, y):
    """Record a player's new position. Returns ``(code, player)``."""
    entry = _sid_index.get(sid)
    if entry is None:
        return None, None

    x, y = _clean_coord(x), _clean_coord(y)
    if x is None or y is None:
        return None, None

    code, key = entry
    room = _rooms.get(code)
    player = room["players"].get(key) if room else None
    if player is None or not player["in_game"]:
        return None, None

    player["x"], player["y"] = x, y
    return code, player


def reset():
    """Drop all state. For tests."""
    _rooms.clear()
    _sid_index.clear()
