# -*- coding: utf-8 -*-
"""The round: roles, counting, tagging, rescues and winning.

One player is the seeker. Everyone starts on the home base in the middle
of the house, the seeker counts to twenty with their eyes shut, and the
rest scatter. Then the seeker hunts. A tagged hider is frozen where they
stand until a free hider walks into them. The seeker wins by freezing
everyone; the hiders win by getting every one of themselves back onto the
base. Anything short of one of those two — somebody home while somebody
else is still out there — is a position rather than a result, and the
round plays on until the clock decides it.

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


def _bearing_difference(viewer, target):
    """Angle between where ``viewer`` is looking and where ``target`` is.

    Signed, and wrapped to (-pi, pi], so that a target just clockwise of
    straight ahead is a small number rather than nearly a full turn.
    """
    vx, vy = _center(viewer)
    tx, ty = _center(target)

    bearing = math.atan2(ty - vy, tx - vx)
    return math.remainder(bearing - viewer.get("facing", 0.0), 2 * math.pi)


def _in_torchlight(viewer, target, rules):
    """Whether a seeker carrying a torch rather than a lantern sees this.

    The beam is narrow but reaches further than the all-round sight the
    mode leaves everyone else, so a seeker sees a long way down a
    corridor and nothing at all beside them — which is the point, since
    it means they can be walked around behind.
    """
    distance = _distance(viewer, target)

    # Arm's length. You do not have to be looking at somebody you are
    # close enough to touch, and a hider being invisible while stood on
    # the seeker's toes would read as a bug rather than as a rule.
    if distance <= config.TAG_DISTANCE * 2:
        return True

    if distance > rules["cone_reach"]:
        return False

    half_beam = math.radians(rules["cone_degrees"]) / 2
    return abs(_bearing_difference(viewer, target)) <= half_beam


# ---------------------------------------------------------------------------
# Who is who
# ---------------------------------------------------------------------------

def _tagger(room):
    """The seeker the round *started* with, or None if they are gone.

    Only used for display. Modes that turn the tagged into hunters have
    several seekers by the end, and this stays the one it began with, so
    the HUD can go on saying whose round it was.
    """
    key = _state(room)["tagger"]
    player = room["players"].get(key) if key else None
    return player if player and player["role"] == "tagger" else None


def _taggers(room):
    """Everyone hunting right now.

    A list rather than one record, because a mode that converts the
    tagged ends up with a houseful of them.
    """
    return [p for p in room["players"].values() if p["role"] == "tagger"]


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

    chosen = random.choice(_candidates(room, game, [key for key, _ in players]))

    mode = rooms.mode_of(room)
    rules = modes.get(mode)

    game.update(
        phase="gathering",
        tagger=chosen,
        map=config.DEFAULT_MAP,
        mode=mode,
        phase_ends_at=_now() + config.GATHER_SECONDS,
        round_ends_at=None,
        winner=None,
        note=None,
    )

    # Usually the chosen player is the seeker and everybody else hides.
    # Sardines turns that round: one player hides and the whole room comes
    # looking, so the same pick means the opposite role.
    inverted = rules["seekers"] == "all_but_one"

    for index, (key, player) in enumerate(players):
        odd_one_out = key == chosen
        if inverted:
            player["role"] = "hider" if odd_one_out else "tagger"
        else:
            player["role"] = "tagger" if odd_one_out else "hider"
        player["state"] = "free"
        player["pinned_until"] = None
        # Back to the base, whatever happened last round.
        player["x"], player["y"] = maps.spawn_point(game["map"], index)

    return True, None


def _candidates(room, game, keys):
    """Who is in the draw to be the odd one out this round.

    Anybody who put their hand up in the lobby, if anybody did. Wanting
    to be the seeker is the best possible reason to be one, and it beats
    the rotation outright: somebody who volunteers two rounds running is
    asking, not being landed with it.

    Failing that, an even draw among everybody — minus whoever had it
    last round, so the same person is not it twice in a row when there is
    somebody else to pick. With only one candidate left that falls back
    to them, or nobody would be seeking at all.
    """
    offered = rooms.volunteers(room)
    if offered:
        return offered

    return [key for key in keys if key != game["last_tagger"]] or keys


def reset(code):
    """Forget the round, e.g. once everyone is back in the lobby."""
    room = rooms.get(code)
    if room is None:
        return

    room["game"] = _new_state()
    for player in room["players"].values():
        player["role"] = None
        player["state"] = "free"
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


def can_stand(room, player, x, y):
    """May this player be at this position, wherever they came from?

    The base is the one patch of floor the seeker does not get. Standing
    on it, they could not be run past, and the last hider would have
    nowhere left to go — the round would end by somebody parking on the
    finish line. So it is a wall to them, drawn nowhere and enforced
    here, since a client that has been edited to walk through it is
    exactly the client that would.

    A seeker who is somehow already inside is let out rather than pinned
    there, so a bug in the placement code cannot become a stuck player.
    """
    game = _state(room)

    if player["role"] != "tagger" or game["phase"] != "hunting":
        return True
    # Nothing to defend in a mode where home is only a rug.
    if not _rules(game)["home_is_safety"]:
        return True

    size = config.PLAYER_SIZE
    if maps.touches_base(game["map"], player["x"], player["y"], size):
        return True

    return not maps.touches_base(game["map"], x, y, size)


def can_see(room, viewer, target):
    """Should ``viewer`` be sent ``target``'s position?

    The filter lives on the server so that hiding actually hides. Four
    things can conceal somebody: distance, a wall, the seeker's shut eyes
    during the count, and a hiding spot that has not been searched yet.

    The wall is the one that makes the house a house. Sight used to reach
    straight through the building, so standing in the study you could
    watch the seeker cross the kitchen — the rooms were decoration and
    the only real hiding place was distance. Now you see what is in front
    of you and nothing through the plaster, and a doorway is worth
    something.
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

    if rules["cone_degrees"] is not None and viewer["role"] == "tagger":
        if not _in_torchlight(viewer, target, rules):
            return False
    elif distance > rules["vision_radius"]:
        return False

    # Nothing is seen through a wall, by anybody, in any mode. Applied
    # after the cheap distance test, since most pairs never get here.
    vx, vy = _center(viewer)
    tx, ty = _center(target)
    if maps.blocks_sight(game["map"], vx, vy, tx, ty):
        return False

    # Team-mates can see each other hiding, which is what makes rescues
    # possible; the seeker has to come and search the furniture. A frozen
    # player is always visible, so they can be found and thawed.
    if (viewer["role"] == "tagger"
            and target["role"] == "hider"
            and rules["hiding_conceals"]
            and target["state"] == "free"
            and _hidden_in(game, target)):
        return distance <= config.SEARCH_DISTANCE

    return True


# ---------------------------------------------------------------------------
# Shouting
# ---------------------------------------------------------------------------

def _nearness(distance):
    if distance <= config.SHOUT_CLOSE:
        return "close"
    if distance <= config.SHOUT_NEARBY:
        return "nearby"
    return "far"


def _rounded_bearing(listener, shouter):
    """Which way the noise came from, to the nearest few degrees.

    Rounded on purpose. An exact bearing plus a distance is a position,
    and handing one to every client in earshot would undo the whole point
    of filtering positions in the first place. Rounded, it points at a
    room.
    """
    lx, ly = _center(listener)
    sx, sy = _center(shouter)

    step = math.radians(config.SHOUT_BEARING_DEGREES)
    return round(math.atan2(sy - ly, sx - lx) / step) * step


def earshot(room, shouter):
    """Everyone who hears a shout, and roughly where it came from.

    Sound is the one thing in the house that goes through walls — that is
    what makes shouting worth a button. It is also what makes it a risk,
    since the seeker has ears too, and a hider who says "clear" has just
    told them which end of the house to search.

    Yields ``(listener, payload)``. What is in the payload is a bearing
    and one of three words for distance, never a coordinate.
    """
    heard = []

    for listener in room["players"].values():
        if listener is shouter or listener["sid"] is None:
            continue
        if not listener["in_game"]:
            continue

        distance = _distance(listener, shouter)
        if distance > config.SHOUT_HEAR_RADIUS:
            continue

        heard.append((listener, {
            "name": shouter["name"],
            "emoji": shouter["emoji"],
            "role": shouter["role"],
            "state": shouter["state"],
            "bearing": _rounded_bearing(listener, shouter),
            "nearness": _nearness(distance),
        }))

    return heard


def can_shout(room, player, now=None):
    """May this player make a noise right now?

    Only once there is a round to shout into, and only every so often, so
    that holding the key down is not a siren. Being frozen is no bar —
    "I am over here and I need somebody" is the single most useful thing
    a tagged player can say.
    """
    phase = _state(room)["phase"]
    if phase not in ("counting", "hunting"):
        return False

    now = _now() if now is None else now
    return now - player["shouted_at"] >= config.SHOUT_COOLDOWN_SECONDS


def mark_shouted(player, now=None):
    player["shouted_at"] = _now() if now is None else now


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
    """One pass of contact, thawing, reaching home, and checking for a win."""
    rules = _rules(game)

    inverted = rules["seekers"] == "all_but_one"

    if not _taggers(room):
        # Not reachable in an inverted mode by everyone being found —
        # that ends the round as a win before this runs again.
        _finish(game, None, "Everybody looking left the game."
                if inverted else "The seeker left the game.")
        return {"players"}
    if not _hiders(room):
        _finish(game, None, "The player hiding left the game."
                if inverted else "Everybody hiding left the game.")
        return {"players"}

    changes = _contacts(room, game, rules)

    if rules["rescues"]:
        changes |= _rescues(_hiders(room))

    changes |= _outcome(room, game, rules, now)
    return changes


def _contacts(room, game, rules):
    """Who is standing on home, and who a seeker has caught up with.

    Re-read each pass rather than taken as an argument, because a mode
    that moves players between the two sides does so as this runs.

    Safety is a *place*, not something you win and keep. A hider is safe
    for exactly as long as they are stood on the base and is fair game
    again the moment they step off it — otherwise touching home once
    bought immunity for the rest of the round, and people wandered back
    out through the middle of a hunt untouchable.
    """
    if rules["on_tag"] == "recruit":
        return _joining(room)

    changes = set()

    # A seeker whose socket is gone is not in the house to touch anyone.
    taggers = [t for t in _taggers(room) if t["sid"] is not None]

    for hider in _hiders(room):
        # Being frozen outranks where you are standing; a tagged player
        # dropped on the base is still tagged.
        if hider["state"] == "frozen":
            continue

        # Checked before a tag, so a dive for the door is worth trying:
        # crossing the line in the same moment beats the touch.
        if rules["home_is_safety"]:
            home = maps.in_base(game["map"], *_center(hider))
            wanted = "safe" if home else "free"
            if hider["state"] != wanted:
                hider["state"] = wanted
                changes.add("players")
            if home:
                continue

        if not any(_distance(t, hider) <= config.TAG_DISTANCE for t in taggers):
            continue

        if rules["on_tag"] == "convert":
            # The tagged join the hunt instead of stopping. Every catch is
            # one fewer to find and one more pair of eyes looking for the
            # rest, so the round gets faster as it goes.
            hider["role"] = "tagger"
            hider["state"] = "free"
            # Their own sight lines change with their side, and so does
            # everyone else's view of them.
            changes.add("sight")
        else:
            hider["state"] = "frozen"

        changes.add("players")

    return changes


def _joining(room):
    """Sardines: a seeker who finds the hidden squeezes in beside them.

    Contact is read the other way round from every other mode. It is the
    seeker who changes sides, not the person they walked into, and the
    result is that the hiding place fills up while the search gets
    lonelier — which is the whole joke of the game.
    """
    changes = set()

    hidden = [h for h in _hiders(room) if h["sid"] is not None]
    if not hidden:
        return changes

    for seeker in _taggers(room):
        if seeker["sid"] is None:
            continue
        if not any(_distance(seeker, h) <= config.TAG_DISTANCE for h in hidden):
            continue

        seeker["role"] = "hider"
        seeker["state"] = "free"
        # They see the house as a hider now, and the hiders see them.
        changes.add("sight")
        changes.add("players")

    return changes


def _outcome(room, game, rules, now):
    """End the round if somebody has won it.

    There are exactly three ways a hunt finishes: every hider frozen,
    every hider home, or the clock running out. Any mixture of the two
    states is still a live round — somebody home while somebody else is
    frozen is a position, not a result, and ending there took the round
    away from players who were still in it.
    """
    if rules["seekers"] == "all_but_one":
        return _sardines_outcome(room, game, now)

    # Everybody the round is still waiting on, including anyone whose
    # phone dropped a moment ago. A socket that stays gone is dealt with
    # by rooms.py dropping the player after the grace period, which is
    # what stops a lost connection either ending the round on the spot or
    # holding it open forever.
    hiders = _hiders(room)

    if not hiders:
        # Nobody is hiding any more. Where a tag recruits the tagged that
        # is the seekers having taken the whole house, rather than the
        # broken round it would be in any other mode.
        if rules["on_tag"] == "convert":
            _finish(game, "tagger", None)
            return {"players"}
    elif all(h["state"] == "safe" for h in hiders):
        _finish(game, "hiders", None)
        return {"players"}
    elif all(h["state"] == "frozen" for h in hiders):
        _finish(game, "tagger", None)
        return {"players"}

    if now >= game["round_ends_at"]:
        _finish(game, "tagger", "Time ran out.")
        return {"players"}

    return set()


def _sardines_outcome(room, game, now):
    """Sardines ends when there is nobody left to be looking.

    The hiding side always wins, because everyone ends up on it; what the
    round is really deciding is who was last to work out where everybody
    went, and that is the one thing worth reporting.
    """
    seekers = [t for t in _taggers(room) if t["sid"] is not None]

    if not seekers:
        _finish(game, "hiders", None)
        return {"players"}

    # With two players there is only ever one seeker, so waiting for the
    # last one to be left would end the round before it began. Above that,
    # being the last one still looking is how you lose.
    present = sum(1 for p in room["players"].values() if p["sid"] is not None)
    if len(seekers) == 1 and present >= 3:
        _finish(game, "hiders", f"{seekers[0]['name']} was last to find them.")
        return {"players"}

    if now >= game["round_ends_at"]:
        _finish(game, "hiders", "Time ran out. They hid too well.")
        return {"players"}

    return set()


def _rescues(hiders):
    """Thaw frozen hiders a free team-mate has run into.

    Contact, nothing more: you walk through somebody and they are up
    again. Holding position for a second and a half used to be the price,
    and on the screen it was indistinguishable from standing about doing
    nothing — people arrived, waited, gave up and never learned they had
    almost done it. The cost is the trip, which is across open floor with
    a seeker somewhere in the house, and that was always the real one.

    Only free hiders can thaw anyone. Somebody who already made it home
    is out of play, so they cannot wander back out and rescue the rest
    with no risk to themselves.
    """
    changes = set()
    rescuers = [h for h in hiders if h["state"] == "free"]

    for frozen in hiders:
        if frozen["state"] != "frozen":
            continue

        if any(_distance(frozen, rescuer) <= config.RESCUE_DISTANCE
               for rescuer in rescuers):
            frozen["state"] = "free"
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
    chosen = room["players"].get(game["tagger"]) if game["tagger"] else None

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
        # The numbers that vary by mode, so the client draws the round it
        # is actually in rather than the one config.py describes. The
        # server still decides everything these affect; sending them only
        # stops the drawing disagreeing with the ruling.
        "rules": {
            "visionRadius": rules["vision_radius"],
            "hidingConceals": rules["hiding_conceals"],
            "homeIsSafety": rules["home_is_safety"],
            "rescues": rules["rescues"],
            "coneDegrees": rules["cone_degrees"],
            "coneReach": rules["cone_reach"],
        },
        # Counted down by the client from when it arrives, so the clock
        # keeps ticking between broadcasts.
        "secondsLeft": _seconds_left(game["phase_ends_at"], now),
        "roundSecondsLeft": _seconds_left(game["round_ends_at"], now),
        "tagger": tagger["name"] if tagger else None,
        # The player the round singled out, whichever side that put them
        # on. Usually the seeker; in Sardines it is the one who hid, and
        # the HUD has to be able to name them either way.
        "chosen": chosen["name"] if chosen else None,
        "winner": game["winner"],
        "note": game["note"],
        "players": players,
        "tally": {
            "hiders": len(hiders),
            "free": sum(1 for p in hiders if p["state"] == "free"),
            "frozen": sum(1 for p in hiders if p["state"] == "frozen"),
            "safe": sum(1 for p in hiders if p["state"] == "safe"),
            # Worth counting separately: in a mode where the tagged change
            # sides this climbs through the round, and "one seeker" stops
            # being a true thing to say.
            "seekers": sum(1 for p in players if p["role"] == "tagger"),
        },
    }
