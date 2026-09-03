# -*- coding: utf-8 -*-
"""The round: roles, counting, tagging, rescues and winning.

One player is the seeker. Everyone starts on the home base in the middle
of the house, the seeker counts to twenty with their eyes shut, and the
rest scatter. Then the seeker hunts. A tagged hider is frozen where they
stand until a free hider stands with them long enough to thaw them. The
seeker wins by freezing everyone; the hiders win by getting every one of
themselves back onto the base.

Everything here is server-authoritative. Clients are told what their
role is and what phase the round is in, but they do not get to decide who
is frozen, who is home, or who can see whom — otherwise the game would
be one edited file away from pointless.

The phases, in order:

``lobby``      no round yet, or the last one is forgotten
``gathering``  everyone pinned to the base while the last clients load
``counting``   the seeker is blind and rooted; the hiders scatter
``hunting``    open season
``over``       somebody won; the host can start another round
"""

import math
import random
import time

import config
import maps
import modes
import rooms

# Nobody moves while the last clients are still loading in.
_STILL_PHASES = ("gathering",)


def _now():
    return time.monotonic()


def _new_state():
    return {
        "phase": "lobby",
        # Player key of the seeker, so it survives them renaming nothing
        # and reconnecting.
        "tagger": None,
        # Who it was last round, so the same person is not picked twice
        # in a row when there is a choice.
        "last_tagger": None,
        "map": config.DEFAULT_MAP,
        # Copied from the room when the round starts, so that the host
        # changing the lobby's selection cannot rewrite the rules of a
        # hunt that is already under way.
        "mode": modes.DEFAULT_MODE,
        # Deadline for the current phase, and for the hunt as a whole.
        "phase_ends_at": None,
        "round_ends_at": None,
        "winner": None,
        # Why the round ended, when it was not a clean win.
        "note": None,
        # Players the round has just picked up and put down somewhere
        # else, waiting to be told about it. Drained by the caller.
        "relocated": [],
        # Rate limit for move-driven resolution.
        "resolved_at": 0.0,
    }


def state(code):
    """The round state for a room, created on first use. None if no room."""
    room = rooms.get(code)
    return None if room is None else _state(room)


def _state(room):
    if room.get("game") is None:
        room["game"] = _new_state()
    return room["game"]


def _rules(game):
    """The mode's answers for the round in progress. See :mod:`modes`."""
    return modes.get(game["mode"])


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def _center(player):
    """Players are stored by their top-left corner; distances want centres."""
    half = config.PLAYER_SIZE / 2
    return player["x"] + half, player["y"] + half


def _distance(a, b):
    ax, ay = _center(a)
    bx, by = _center(b)
    return math.hypot(ax - bx, ay - by)


def _distance_to_base(game, player):
    cx, cy = _center(player)
    bx, by = maps.base_center(game["map"])
    return math.hypot(cx - bx, cy - by)


def _hidden_in(game, player):
    """The hiding spot a player is tucked into, or None."""
    return maps.hiding_spot_at(game["map"], *_center(player))


# ---------------------------------------------------------------------------
# Who is who
# ---------------------------------------------------------------------------

def _tagger(room):
    """The seeker's record, or None if they are gone."""
    key = _state(room)["tagger"]
    player = room["players"].get(key) if key else None
    return player if player and player["role"] == "tagger" else None


def _hiders(room):
    """Hiders who are actually in the world."""
    return [
        p for p in room["players"].values()
        if p["role"] == "hider" and p["in_game"]
    ]


# ---------------------------------------------------------------------------
# Starting a round
# ---------------------------------------------------------------------------

def start(code):
    """Begin a round. Returns ``(ok, message)``.

    Called when the host presses start, so it validates rather than
    trusting that the lobby only offered the button when it was sensible.
    """
    room = rooms.get(code)
    if room is None:
        return False, "Room not found"

    game = _state(room)

    # Deliberately not refused mid-round. The host is the authority on
    # when a round starts, and a host who has backed out to the lobby
    # while the rest are still hunting would otherwise have no way to
    # call the whole thing off and deal again.
    players = list(room["players"].items())
    if len(players) < config.MIN_PLAYERS:
        return False, f"You need at least {config.MIN_PLAYERS} players"

    # Spread the seeker around: anyone but last round's seeker, unless
    # they are the only candidate left.
    keys = [key for key, _ in players]
    candidates = [key for key in keys if key != game["last_tagger"]] or keys
    tagger = random.choice(candidates)

    game.update(
        phase="gathering",
        tagger=tagger,
        map=config.DEFAULT_MAP,
        mode=rooms.mode_of(room),
        phase_ends_at=_now() + config.GATHER_SECONDS,
        round_ends_at=None,
        winner=None,
        note=None,
    )

    for index, (key, player) in enumerate(players):
        player["role"] = "tagger" if key == tagger else "hider"
        player["state"] = "free"
        player["rescue_since"] = None
        player["pinned_until"] = None
        # Back to the base, whatever happened last round.
        player["x"], player["y"] = maps.spawn_point(game["map"], index)

    return True, None


def reset(code):
    """Forget the round, e.g. once everyone is back in the lobby."""
    room = rooms.get(code)
    if room is None:
        return

    room["game"] = _new_state()
    for player in room["players"].values():
        player["role"] = None
        player["state"] = "free"
        player["rescue_since"] = None
        player["pinned_until"] = None


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def can_move(room, player):
    """Is this player allowed to move themselves right now?

    The seeker is rooted while they count — that is what makes counting a
    cost rather than a formality — and a frozen hider is frozen. With no
    round running you are free to wander the house, so that opening the
    game page on its own is not a dead screen.
    """
    game = _state(room)

    if game["phase"] in _STILL_PHASES:
        return False
    if game["phase"] == "counting":
        return player["role"] != "tagger"
    if game["phase"] == "hunting":
        if player["state"] == "frozen":
            return False
        pinned = player["pinned_until"]
        return pinned is None or _now() >= pinned

    return True


def can_see(room, viewer, target):
    """Should ``viewer`` be sent ``target``'s position?

    The filter lives on the server so that hiding actually hides. Three
    things can conceal somebody: distance, the seeker's shut eyes during
    the count, and a hiding spot that has not been searched yet.
    """
    if viewer is target:
        return True

    game = _state(room)
    phase = game["phase"]

    # Nothing to hide before the round starts or after it ends.
    if phase in ("lobby", "gathering", "over"):
        return True

    # Eyes shut. The seeker gets nothing at all while counting, so they
    # cannot simply watch where everyone runs.
    if phase == "counting" and viewer["role"] == "tagger":
        return False

    rules = _rules(game)

    distance = _distance(viewer, target)
    if distance > rules["vision_radius"]:
        return False

    # Team-mates can see each other hiding, which is what makes rescues
    # possible; the seeker has to come and search the furniture. A frozen
    # player is always visible, so they can be found and thawed.
    if (viewer["role"] == "tagger"
            and rules["hiding_conceals"]
            and target["state"] == "free"
            and _hidden_in(game, target)):
        return distance <= config.SEARCH_DISTANCE

    return True


# ---------------------------------------------------------------------------
# Advancing the round
# ---------------------------------------------------------------------------

def resolve(code, force=False):
    """Bring a room's round up to date. Returns the set of things changed.

    ``"phase"`` in the result means visibility rules may have changed too,
    so callers should resync who can see whom. ``"players"`` means a role
    or a frozen/safe state moved.

    Called both from a background tick and from every position update, so
    that a tag lands as soon as the two players touch rather than up to a
    tick later. The rate limit keeps sixty updates a second per player
    from meaning sixty full passes each.
    """
    room = rooms.get(code)
    if room is None:
        return set()

    game = _state(room)
    if game["phase"] == "lobby":
        return set()

    now = _now()
    if not force and now - game["resolved_at"] < config.RESOLVE_INTERVAL_SECONDS:
        return set()
    game["resolved_at"] = now

    changes = set()
    before = game["phase"]

    if game["phase"] == "gathering" and _everyone_ready(room, game, now):
        _begin_counting(game, now)
    if game["phase"] == "counting" and now >= game["phase_ends_at"]:
        _begin_hunting(room, game, now)
    if game["phase"] == "hunting":
        changes |= _hunt(room, game, now)

    if game["phase"] != before:
        changes.add("phase")
    if game["relocated"]:
        changes.add("moved")

    return changes


def take_relocated(code):
    """Players the round has moved, clearing the list as it hands them over.

    They have to be told where they now are, or their client carries on
    drawing them — and reporting them — somewhere else entirely.
    """
    room = rooms.get(code)
    if room is None:
        return []

    game = _state(room)
    moved, game["relocated"] = game["relocated"], []
    return moved


def _everyone_ready(room, game, now):
    """Has everybody loaded the game page, or have we waited long enough?"""
    if now >= game["phase_ends_at"]:
        return True

    connected = [p for p in room["players"].values() if p["sid"] is not None]
    return bool(connected) and all(p["in_game"] for p in connected)


def _begin_counting(game, now):
    game["phase"] = "counting"
    game["phase_ends_at"] = now + config.COUNTDOWN_SECONDS


def _begin_hunting(room, game, now):
    _clear_the_base(room, game, now)

    game["phase"] = "hunting"
    game["phase_ends_at"] = None
    game["round_ends_at"] = now + _rules(game)["round_seconds"]


def _clear_the_base(room, game, now):
    """Move hiders who never left the middle out to a real hiding spot.

    Lurking beside the base and stepping in the moment the count ends is
    not hiding, so the count ending is also the moment that rule is
    enforced.

    Anyone moved is pinned for a moment afterwards. Their client has
    position updates already in flight that still claim the old spot, and
    accepting one would put them straight back where they were told they
    could not stand.
    """
    places = maps.hiding_places(game["map"])
    if not places:
        return

    random.shuffle(places)
    taken = set()

    for hider in _hiders(room):
        if _distance_to_base(game, hider) >= config.NO_HIDE_RADIUS:
            continue

        # Prefer a spot nobody else has just been dropped into.
        spot = next((p for p in places if p not in taken), places[0])
        taken.add(spot)

        hider["x"], hider["y"] = spot
        hider["pinned_until"] = now + config.RELOCATE_PIN_SECONDS
        game["relocated"].append(hider)


def _hunt(room, game, now):
    """One pass of tagging, thawing, reaching home, and checking for a win."""
    changes = set()

    tagger = _tagger(room)
    hiders = _hiders(room)

    if tagger is None:
        _finish(game, None, "The seeker left the game.")
        return {"players"}
    if not hiders:
        _finish(game, None, "Everybody hiding left the game.")
        return {"players"}

    for hider in hiders:
        if hider["state"] != "free":
            continue

        # Home is checked first: stepping onto the base beats a tag, so
        # a dive for the door is worth trying.
        if maps.in_base(game["map"], *_center(hider)):
            hider["state"] = "safe"
            hider["rescue_since"] = None
            changes.add("players")
        elif tagger["sid"] is not None and _distance(tagger, hider) <= config.TAG_DISTANCE:
            hider["state"] = "frozen"
            hider["rescue_since"] = None
            changes.add("players")

    if _rules(game)["rescues"]:
        changes |= _rescues(hiders, now)

    # Anyone still free can change the outcome, so the round is not over.
    present = [h for h in hiders if h["sid"] is not None]
    if present and all(h["state"] != "free" for h in present):
        everyone_home = all(h["state"] == "safe" for h in present)
        _finish(game, "hiders" if everyone_home else "tagger", None)
        changes.add("players")
    elif now >= game["round_ends_at"]:
        _finish(game, "tagger", "Time ran out.")
        changes.add("players")

    return changes


def _rescues(hiders, now):
    """Thaw frozen hiders that a free team-mate has stood with long enough.

    Only free hiders can thaw anyone. Somebody who already made it home
    is out of play, so they cannot wander back out and rescue the rest
    with no risk to themselves.
    """
    changes = set()
    rescuers = [h for h in hiders if h["state"] == "free"]

    for frozen in hiders:
        if frozen["state"] != "frozen":
            continue

        nearby = any(
            _distance(frozen, rescuer) <= config.RESCUE_DISTANCE
            for rescuer in rescuers
        )

        if not nearby:
            # They stepped away, so the next attempt starts from scratch.
            if frozen["rescue_since"] is not None:
                frozen["rescue_since"] = None
            continue

        if frozen["rescue_since"] is None:
            frozen["rescue_since"] = now
            changes.add("players")
        elif now - frozen["rescue_since"] >= config.RESCUE_HOLD_SECONDS:
            frozen["state"] = "free"
            frozen["rescue_since"] = None
            changes.add("players")

    return changes


def _finish(game, winner, note):
    game["phase"] = "over"
    game["winner"] = winner
    game["note"] = note
    game["phase_ends_at"] = None
    game["round_ends_at"] = None
    game["last_tagger"] = game["tagger"]


# ---------------------------------------------------------------------------
# What clients are told
# ---------------------------------------------------------------------------

def _seconds_left(deadline, now):
    if deadline is None:
        return None
    return max(0, int(math.ceil(deadline - now)))


def public_state(code):
    """The round, as broadcast to a whole room.

    Roles and frozen/safe states are public: knowing who the seeker is
    and who still needs rescuing is half the game. Positions are the only
    secret, and those go out one client at a time through
    :func:`can_see`.
    """
    room = rooms.get(code)
    if room is None:
        return None

    game = _state(room)
    now = _now()
    tagger = _tagger(room)

    players = [
        {
            "name": p["name"],
            "emoji": p["emoji"],
            "role": p["role"],
            "state": p["state"],
            "isHost": p["isHost"],
            "connected": p["sid"] is not None,
            "inGame": p["in_game"],
        }
        for p in room["players"].values()
    ]

    hiders = [p for p in players if p["role"] == "hider"]

    rules = _rules(game)

    return {
        "phase": game["phase"],
        "mode": rules["id"],
        "modeName": rules["name"],
        # Counted down by the client from when it arrives, so the clock
        # keeps ticking between broadcasts.
        "secondsLeft": _seconds_left(game["phase_ends_at"], now),
        "roundSecondsLeft": _seconds_left(game["round_ends_at"], now),
        "tagger": tagger["name"] if tagger else None,
        "winner": game["winner"],
        "note": game["note"],
        "players": players,
        "tally": {
            "hiders": len(hiders),
            "free": sum(1 for p in hiders if p["state"] == "free"),
            "frozen": sum(1 for p in hiders if p["state"] == "frozen"),
            "safe": sum(1 for p in hiders if p["state"] == "safe"),
        },
    }
