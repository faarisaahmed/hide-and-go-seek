# -*- coding: utf-8 -*-
"""Socket.IO event handlers.

Both pages open a socket. The lobby sends ``join_lobby`` just to subscribe
to room broadcasts; the game page sends ``join_game``, which also places
the player in the world.

Naming note: Socket.IO rooms and game rooms line up exactly here, since
every client subscribes to the Socket.IO room named after its room code.
``flask_socketio.join_room`` is aliased to keep it distinct from our own
room helpers.

Positions are the one thing *not* broadcast to a whole room. Each move is
sent only to the players who are allowed to see the mover, which is what
makes a hiding spot worth using: a client cannot draw what it was never
sent. See ``game.can_see``.
"""

from flask import request
from flask_socketio import emit
from flask_socketio import join_room as subscribe_to_room

import config
import game
import rooms
from extensions import socketio


def _world_payload(player):
    """How a player appears to someone who can see them.

    Role and frozen/safe state are deliberately absent: those are public
    and arrive in the room-wide ``game_state``, keyed by name, so they do
    not have to be chased through every position update.
    """
    return {
        "id": player["sid"],
        "name": player["name"],
        "emoji": player["emoji"],
        "x": player["x"],
        "y": player["y"],
    }


def _reject(message):
    emit("join_rejected", {"message": message})


# ---------------------------------------------------------------------------
# Visibility
# ---------------------------------------------------------------------------

def _update_view(room, viewer, target, moved=None):
    """Keep one viewer's picture of one target honest.

    ``player_revealed`` carries everything needed to start drawing
    somebody, so the cheap ``player_moved`` updates that follow can be
    just an id and a position. ``player_hidden`` is sent once, when they
    slip out of sight, rather than on every frame they stay out of it.
    """
    sid = viewer["sid"]
    if sid is None:
        return

    if game.can_see(room, viewer, target):
        if sid in target["seen_by"]:
            if moved is not None:
                socketio.emit("player_moved", moved, to=sid)
        else:
            target["seen_by"].add(sid)
            socketio.emit("player_revealed", _world_payload(target), to=sid)
    elif sid in target["seen_by"]:
        target["seen_by"].discard(sid)
        socketio.emit("player_hidden", {"id": target["sid"]}, to=sid)


def _relay_position(room, code, mover):
    """Tell whoever can see the mover where they are now.

    Both directions are checked, because moving can just as easily bring
    somebody standing still into view — a seeker walking up to a wardrobe
    is exactly that case.
    """
    moved = {"id": mover["sid"], "x": mover["x"], "y": mover["y"]}

    for other in rooms.players_in_game(code, exclude_sid=mover["sid"]):
        _update_view(room, other, mover, moved)
        _update_view(room, mover, other)


def _sync_visibility(code):
    """Recheck every pair, for when the rules changed rather than a position.

    The count ending and the round ending both open eyes that were shut,
    and no position update need arrive to make that true.
    """
    room = rooms.get(code)
    if room is None:
        return

    world = rooms.players_in_game(code)
    for viewer in world:
        for target in world:
            if viewer is not target:
                _update_view(room, viewer, target)


# ---------------------------------------------------------------------------
# Broadcasting the round
# ---------------------------------------------------------------------------

def _publish(code, changes=("players",)):
    """Push the round state to a room, resyncing sight lines if needed."""
    # Corrections first: sight lines depend on where people actually are.
    if "moved" in changes:
        for player in game.take_relocated(code):
            _correct(player)

    if "phase" in changes:
        _sync_visibility(code)

    state = game.public_state(code)
    if state is not None:
        socketio.emit("game_state", state, to=code)


def _correct(player):
    """Tell one client where the server says it is."""
    if player["sid"] is None:
        return

    socketio.emit("position_correction",
                  {"x": player["x"], "y": player["y"]},
                  to=player["sid"])


def _place_everyone(code):
    """Tell each client where the new round put them.

    Starting a round moves everybody back to the base, so clients that
    are already on the game page would otherwise keep drawing themselves
    wherever they were standing when the last one ended.
    """
    for player in rooms.players_in_game(code):
        _correct(player)


# ---------------------------------------------------------------------------
# The clock
# ---------------------------------------------------------------------------

_ticking = False


def _ensure_ticking():
    """Start the round clock, once, on the first round of the process.

    Timers cannot rely on position updates to advance them: during the
    count the seeker is not moving at all, and a round with everybody
    standing still still has to end.
    """
    global _ticking
    if _ticking:
        return

    _ticking = True
    socketio.start_background_task(_tick)


def _tick():
    while True:
        socketio.sleep(config.GAME_TICK_SECONDS)

        for code in rooms.active_codes():
            # One bad room must not stop the clock for every other room,
            # and there is nobody to hand the exception to out here.
            try:
                changes = game.resolve(code, force=True)
                if changes:
                    _publish(code, changes)
            except Exception:  # noqa: BLE001
                continue


# ---------------------------------------------------------------------------
# Lobby
# ---------------------------------------------------------------------------

@socketio.on("join_lobby")
def on_join_lobby(data):
    """A lobby page is asking to receive this room's broadcasts."""
    code = rooms.clean_code(data.get("code"))
    name = data.get("name")

    if rooms.attach(request.sid, code, name) is None:
        _reject("That room has closed.")
        return

    subscribe_to_room(code)

    # Being in the lobby means being out of the world. Once the last
    # player has backed out, the round is finished with rather than
    # sitting there half-played.
    if not rooms.players_in_game(code):
        game.reset(code)

    emit("room_updated", rooms.public_view(code))
    _publish(code)


@socketio.on("start_game_request")
def on_start_game(data):
    """The host started a round.

    Sent from the lobby to begin, and from the game page to play again;
    both mean the same thing, so both land here. Everyone is bounced to
    the game page, which is a no-op for those already on it.
    """
    player = rooms.connected_player(request.sid)
    if player is None or not player["isHost"]:
        # Only the host starts a round, whatever a client claims.
        return

    code = rooms.room_code_of(request.sid)
    ok, message = game.start(code)
    if not ok:
        emit("start_rejected", {"message": message})
        return

    _ensure_ticking()

    emit("trigger_start_game", to=code)
    _place_everyone(code)
    _publish(code, {"phase", "players"})


# ---------------------------------------------------------------------------
# The game world
# ---------------------------------------------------------------------------

@socketio.on("join_game")
def on_join_game(data):
    """A game page is entering the world."""
    code = rooms.clean_code(data.get("code"))
    name = data.get("name")

    game_state = game.state(code)
    map_name = game_state["map"] if game_state else config.DEFAULT_MAP

    player = rooms.enter_game(request.sid, code, name, map_name)
    if player is None:
        _reject("That room has closed.")
        return

    subscribe_to_room(code)
    room = rooms.get(code)

    # Only the players this one is allowed to see, so a client that joins
    # mid-hunt does not get handed the hiding places.
    visible = [
        other for other in rooms.players_in_game(code, exclude_sid=request.sid)
        if game.can_see(room, player, other)
    ]
    for other in visible:
        other["seen_by"].add(request.sid)

    # Where to stand, which map to load, who is in sight, and what the
    # round is doing — one message, so the client can start in one step.
    emit("game_joined", {
        "map": map_name,
        "you": _world_payload(player),
        "players": [_world_payload(other) for other in visible],
        "game": game.public_state(code),
    })

    # Everyone else finds out about them if they are in range.
    for other in rooms.players_in_game(code, exclude_sid=request.sid):
        _update_view(room, other, player)

    # The last client loading is what ends the "get ready" phase.
    _publish(code, game.resolve(code, force=True) | {"players"})


@socketio.on("player_move")
def on_player_move(data):
    """A client reported a new position."""
    if not isinstance(data, dict):
        return

    code = rooms.room_code_of(request.sid)
    room = rooms.get(code) if code else None
    player = rooms.connected_player(request.sid)
    if room is None or player is None or not player["in_game"]:
        return

    if game.can_move(room, player):
        _, moved = rooms.move(request.sid, data.get("x"), data.get("y"))
        if moved is not None:
            _relay_position(room, code, moved)
    else:
        _hold_still(player, data)

    # Deliberately after the move rather than before it, so a tag lands
    # on the update that makes contact instead of a tick later. The
    # phase itself is advanced by the clock, so nothing is lost by not
    # looking before we move.
    changes = game.resolve(code)
    if changes:
        _publish(code, changes)


def _hold_still(player, data):
    """Put a client back where the server says it is.

    Clients gate their own movement while counting or frozen, so this is
    a backstop for one that is out of step — or lying. Only sent when the
    client actually disagrees, or a frozen player's keepalives would draw
    a correction every second for nothing.
    """
    x, y = data.get("x"), data.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return

    if abs(x - player["x"]) > 0.5 or abs(y - player["y"]) > 0.5:
        emit("position_correction", {"x": player["x"], "y": player["y"]})


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
    _publish(code, game.resolve(code, force=True) | {"players"})
