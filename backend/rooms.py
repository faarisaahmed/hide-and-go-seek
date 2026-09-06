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

import math
import random
import time

import config
import maps
import modes

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

    # Whoever has been here longest takes over if the host is gone —
    # somebody real, since a bot cannot press start.
    if not any(p["isHost"] for p in room["players"].values()):
        heir = next((p for p in room["players"].values() if not p["is_bot"]),
                    None)
        if heir is not None:
            heir["isHost"] = True

    return room


def _expire_all():
    for code in list(_rooms):
        _expire(code)


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------

_bots_made = 0


def _bot_id():
    """A stable id for a bot, in the shape of a socket id but not one.

    Deliberately prefixed: anything that emits to it is emitting into a
    Socket.IO room that does not exist, which is silent rather than an
    error, and the prefix is what makes that obvious in a log.
    """
    global _bots_made
    _bots_made += 1
    return f"bot:{_bots_made}"


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


def _free_color(room):
    """Same, for colours. Two players the same colour is two players you
    cannot tell apart at a glance, which is the whole job."""
    taken = {p["color"] for p in room["players"].values()}
    for color in config.COLOR_POOL:
        if color not in taken:
            return color
    return random.choice(config.COLOR_POOL)


def _new_player(room, name, is_host, is_bot=False):
    return {
        "name": name,
        "emoji": _free_emoji(room),
        "color": _free_color(room),
        "isHost": is_host,
        "x": config.SPAWN_X,
        "y": config.SPAWN_Y,

        # A bot is a player with nobody behind it. It still gets an id in
        # this field, because every other part of the protocol keys off
        # one — who has been told about whom, who moved, who left — and
        # inventing a second kind of identity for the sake of it would
        # mean touching all of that. Nothing is ever emitted to it; see
        # events._update_view.
        "sid": _bot_id() if is_bot else None,
        "is_bot": is_bot,
        # Whatever the bot is currently thinking, owned by bots.py.
        "brain": None,

        # When their socket dropped, or None while connected. Drives expiry.
        # Set at creation too, so a room nobody ever connects to is cleaned
        # up rather than lingering forever. A bot never leaves of its own
        # accord, so it never expires.
        "left_at": None if is_bot else time.monotonic(),
        # True once they have been placed in the world. Survives a dropped
        # socket, which is what lets a reconnect resume in place. A bot is
        # in the world from the moment it is added.
        "in_game": is_bot,

        # Whether they have put their hand up to be the seeker. A
        # standing offer rather than a per-round one: somebody who likes
        # seeking can leave it on and stop being asked.
        "volunteer": False,

        # Round state, owned by game.py. "hider" / "tagger" once a round
        # has started, None in the lobby.
        "role": None,
        # "free", "frozen" (tagged, waiting for a rescue) or "safe" (made
        # it home to the base).
        "state": "free",
        # Set briefly after the server moves them, so their own stale
        # position updates cannot put them back. See game._clear_the_base.
        "pinned_until": None,
        # When a seeker walked into the room the base is in, or None.
        # Loitering there is how a round becomes a staring contest, so it
        # is on a clock. See game._evict_campers.
        "camping_since": None,
        # When they last made a noise, so the shout button has a cooldown
        # on it and holding the key down is not a siren. Kept per player
        # rather than per socket, or reconnecting would reset it.
        "shouted_at": 0.0,
        # Which way they are facing, in radians, as their last movement
        # left them. Only modes that give the seeker a torch rather than
        # a circle of sight care, but it costs nothing to keep current.
        "facing": 0.0,
        # Socket ids this player is currently visible to, so the server
        # only announces someone appearing or vanishing once.
        "seen_by": set(),
    }


def create(host_name):
    """Open a room with ``host_name`` as host. Returns the code, or None."""
    host_name = clean_name(host_name)
    if host_name is None:
        return None

    # Good moment to clear out rooms everyone has already abandoned.
    _expire_all()

    code = _new_room_code()
    # "game" is filled in by game.py the first time it is asked for.
    # "mode" is what the host has selected in the lobby; the round takes a
    # copy of it when it starts, so changing it mid-hunt cannot rewrite
    # the rules of a round already being played.
    room = {"players": {}, "chat": [], "game": None,
            "mode": modes.DEFAULT_MODE}
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
                "color": p["color"],
                "isHost": p["isHost"],
                "connected": p["sid"] is not None,
                "volunteer": p["volunteer"],
                "bot": p["is_bot"],
            }
            for p in room["players"].values()
        ],
        "chat": room["chat"],
        "mode": mode_of(room),
    }


def mode_of(room):
    """The mode a room is set to.

    Read through a helper because rooms outlive code changes: one created
    before a mode was added, or by an older path that did not set the key,
    still has to answer something playable.
    """
    chosen = room.get("mode")
    return chosen if modes.is_mode(chosen) else modes.DEFAULT_MODE


def set_mode(code, mode_id):
    """Point a room at a mode. Returns ``(ok, message)``.

    The caller checks that it was the host asking; this only checks that
    the mode exists, since the id comes from a client.
    """
    room = get(code)
    if room is None:
        return False, "Room not found"

    if not modes.is_mode(mode_id):
        return False, "No such game mode"

    room["mode"] = mode_id
    return True, None


def add_bot(code, name, x, y):
    """Put a bot in a room, already standing in the world.

    Returns the player record, or None if the name is taken. Bots skip
    the lobby entirely: there is nobody to press "join", and a bot that
    had to be waited for would hold up the count.
    """
    room = get(code)
    if room is None or _key(name) in room["players"]:
        return None

    bot = _new_player(room, name, is_host=False, is_bot=True)
    bot["x"], bot["y"] = x, y
    room["players"][_key(name)] = bot
    return bot


def bots_in(room):
    return [p for p in room["players"].values() if p["is_bot"]]


def humans_in(room):
    return [p for p in room["players"].values() if not p["is_bot"]]


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


def set_volunteer(code, name, wants):
    """Put a player's hand up, or take it down. Returns ``(ok, message)``.

    Anybody may volunteer for themselves and nobody may volunteer anybody
    else, which is the only rule worth having here: the point is that
    being the seeker stops being something that happens *to* you.
    """
    room = get(code)
    if room is None:
        return False, "Room not found"

    player = room["players"].get(_key(name)) if isinstance(name, str) else None
    if player is None:
        return False, "You are not in this room"

    player["volunteer"] = bool(wants)
    return True, None


def volunteers(room):
    """Player keys of everyone who has offered to be the seeker."""
    return [key for key, p in room["players"].items() if p["volunteer"]]


def remove_player(code, name):
    """Drop a player from a room for good. Returns ``(ok, message)``.

    Used by the host to remove somebody. Their socket is left connected —
    :mod:`events` tells them they are out and lets their page navigate
    away, which is friendlier than yanking the connection out from under
    a screen that would then just look broken.
    """
    room = get(code)
    if room is None:
        return False, "Room not found"

    player = room["players"].pop(_key(name), None) if isinstance(name, str) else None
    if player is None:
        return False, "They are not in this room"

    # Nobody can see somebody who is no longer in the house.
    if player["sid"] is not None:
        _sid_index.pop(player["sid"], None)
        for other in room["players"].values():
            other["seen_by"].discard(player["sid"])

    return True, None


def set_color(code, name, color):
    """Give a player a new colour. Returns ``(ok, message)``.

    The same shape as :func:`set_emoji`, and for the same reason: what
    makes a colour worth having is that nobody else in the room has it.
    """
    room = get(code)
    if room is None:
        return False, "Room not found"

    if color not in config.COLOR_POOL:
        return False, "That is not one of the available colours"

    player = room["players"].get(_key(name)) if isinstance(name, str) else None
    if player is None:
        return False, "You are not in this room"

    if player["color"] == color:
        return True, None  # already theirs; nothing to do

    if any(p["color"] == color for p in room["players"].values()):
        return False, "Colour already taken!"

    player["color"] = color
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

    # Nobody has been told about this socket yet, whatever the old one saw.
    player["seen_by"] = set()

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
    player["seen_by"] = set()

    # Nobody can see them any more, and nothing is drawing them, so drop
    # the socket from everyone's "already told about this player" set.
    for other in room["players"].values():
        other["seen_by"].discard(sid)

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


def move(sid, x, y, facing=None):
    """Record a player's new position. Returns ``(code, player)``.

    ``facing`` is optional: a client that never sends one simply keeps
    the direction it last had, which is what a player standing still
    would want anyway.
    """
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

    facing = _clean_coord(facing)
    if facing is not None:
        # Wrapped, so a client that counts turns rather than resetting
        # cannot hand us an ever-growing angle.
        player["facing"] = math.remainder(facing, 2 * math.pi)

    return code, player


def reset():
    """Drop all state. For tests."""
    _rooms.clear()
    _sid_index.clear()


def active_codes():
    """Every live room code. A snapshot, so callers can expire rooms."""
    return list(_rooms)
