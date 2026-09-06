# -*- coding: utf-8 -*-
"""Players with nobody behind them.

A room of two is a thin game, and the usual fix — wait for more friends
to be free — is not one this can offer. So the host can add bots, and a
bot is a player record like any other: it has a name, an emoji, a role,
it can be frozen, thawed, tagged and it counts towards winning. What it
does not have is a socket, so nothing is ever sent to it and this module
moves it instead.

They play by the same rules as everybody else, which is the part worth
insisting on. A bot sees through :func:`game.can_see`, so a wall stops it
looking into the next room, furniture conceals a hider from it, and in
Blackout it only sees down its own torch. It walks at roughly a player's
pace with a sprint that runs out. It does not know where anybody is until
it can see them.

What it does have is the house. A bot knows the floor plan and routes
through it door by door (:func:`maps.route`), which is what stops it
walking into a wall and stands in for the thing a human gets for free
after two rounds of playing.

The behaviour rules, in short:

*Seeking* — chase anybody in sight; otherwise work through the hiding
places, nearest first, until they have all been searched, then start
again. Never linger in the room the base is in, which the round would
punish anyway.

*Hiding* — get away from the base and out of sight, then keep moving.
A bot that picked one wardrobe and sat in it until the clock ran out
would be the most tedious opponent imaginable, so they change hiding
place every few seconds, break for home once their nerve runs out, run
from a seeker they can see rather than towards home through them, and
go and thaw a frozen team-mate when there is one to reach.
"""

import math
import random

import config
import game
import maps
import rooms

# Short and human, so a room reads as a room rather than as a server
# rack. The lobby marks them as bots; the names do not have to.
_NAMES = [
    "Robin", "Sam", "Frankie", "Alex", "Jules", "Charlie", "Max",
    "Nico", "Rue", "Kit", "Ash", "Wren",
]

# Enough to make a game of it without exhausting the emoji pool or
# turning the house into a crowd.
MAX_BOTS = 7

# How often a bot reconsiders what it is doing. Ten times a second would
# be both wasteful and twitchy; a third of a second is about how long a
# person takes to change their mind.
_THINK_SECONDS = 0.34

# A waypoint is reached when this close. Loose enough that a bot does not
# jitter on the spot trying to land exactly on a doorway.
_ARRIVED = 26

# Bots walk a shade slower than a person and sprint a shade slower still.
# They make up for it by knowing the floor plan, which is the trade: a
# bot that also moved faster would just be unfair.
_PACE = 0.94
_SPRINT = 1.35
_SPRINT_SECONDS = 3.5
_SPRINT_RECOVER = 6.0

# Barely moving for this long means something is in the way that routing
# did not know about, so throw the plan away and pick another.
_STUCK_SECONDS = 1.2

# A seeker this close is worth running from rather than continuing with
# whatever you were doing.
_ALARM = 300

# A frozen bot calls out every so often. The server would allow one every
# couple of seconds; that would be a smoke alarm rather than a person, so
# they wait longer between shouts than they have to.
_SHOUT_EVERY = 6.0

# How long a noise is worth walking towards. Past this the person who
# made it has moved, and a bot still trudging towards where they used to
# be looks exactly as silly as it is.
_NOISE_LASTS = 9.0

# What a bot makes of the distance words a shout carries. It is told the
# same three bands a player is told, so it guesses the same way a player
# would: somewhere in the middle of the band, in the direction given.
_NOISE_RANGE = {"close": 150, "nearby": 380, "far": 720}

# How long a hider stays put in one place before moving on. The whole
# point: a bot that sat in one wardrobe all round would be no fun to
# play against at all.
_SETTLE_MIN = 5.0
_SETTLE_MAX = 11.0

# And when they do move, they move. Shuffling between two cupboards in
# the same room is camping with extra steps, so the next hiding place has
# to be in a different room *and* a fair walk away — the rooms in this
# house are big enough that one alone was not enough.
_MOVE_AT_LEAST = 340


# ---------------------------------------------------------------------------
# Adding and removing
# ---------------------------------------------------------------------------

def _free_name(room):
    taken = {p["name"].lower() for p in room["players"].values()}

    for name in _NAMES:
        if name.lower() not in taken:
            return name

    # Every name used. Number them rather than refusing, since the cap is
    # what is supposed to stop this getting silly.
    for suffix in range(2, 40):
        for name in _NAMES:
            candidate = f"{name} {suffix}"
            if candidate.lower() not in taken:
                return candidate

    return None


def add(code):
    """Add one bot to a room. Returns ``(ok, message)``."""
    room = rooms.get(code)
    if room is None:
        return False, "Room not found"

    if len(rooms.bots_in(room)) >= MAX_BOTS:
        return False, f"That is as many bots as a house holds ({MAX_BOTS})"

    name = _free_name(room)
    if name is None:
        return False, "No names left"

    state = game.state(code)
    map_name = state["map"] if state else config.DEFAULT_MAP

    # Dropped in beside everybody else. A round already under way puts
    # them wherever the next spawn point is, which is as fair a place to
    # walk into a game as any.
    index = sum(1 for p in room["players"].values() if p["in_game"])
    x, y = maps.spawn_point(map_name, index)

    bot = rooms.add_bot(code, name, x, y)
    if bot is None:
        return False, "Could not add a bot"

    # A bot that joins mid-round is on whichever side needs it: seeking
    # if the round has a seeker already, hiding otherwise. Joining the
    # hunt as a fresh seeker would be a nasty surprise for the hiders.
    if state and state["phase"] not in ("lobby", "over"):
        bot["role"] = "hider"

    return True, None


def remove_one(code):
    """Take the most recently added bot out again. Returns ``(ok, message)``."""
    room = rooms.get(code)
    if room is None:
        return False, "Room not found"

    present = rooms.bots_in(room)
    if not present:
        return False, "There are no bots to remove"

    return rooms.remove_player(code, present[-1]["name"])


def count(code):
    room = rooms.get(code)
    return 0 if room is None else len(rooms.bots_in(room))


# ---------------------------------------------------------------------------
# What a bot is carrying around
# ---------------------------------------------------------------------------

def _brain(bot, now):
    """The bot's working state, made on first use."""
    if bot["brain"] is None:
        bot["brain"] = {
            # Waypoints still to reach, nearest first.
            "path": [],
            # Why we are going there, for the sake of deciding when the
            # plan has gone stale.
            "purpose": None,
            "think_at": 0.0,
            # Hiding places already looked in this sweep, by index.
            "searched": set(),
            # The hiding place we are currently on our way to look in.
            "target": None,
            # Where we were last time and when we last actually got
            # somewhere, so a bot wedged on a corner can notice.
            "was": (bot["x"], bot["y"]),
            "progress_at": now,
            # Sprint, mirroring the shape of the players' bar so a chase
            # is a chase rather than a conveyor belt.
            "sprint": _SPRINT_SECONDS,
            # How long a hider stays in one place before moving on, and
            # how much of the round they will let go by before breaking
            # for home. Rolled per bot, so a room of them does not act
            # as one animal.
            "settle_until": 0.0,
            "nerve": random.uniform(0.3, 0.75),
            # The last noise worth investigating, as the point it seems
            # to have come from, and when we heard it.
            "noise": None,
            "noise_at": 0.0,
            "shouted_at": 0.0,
        }
    return bot["brain"]


def hear(bot, payload, now):
    """Tell a bot about a shout it was in earshot of.

    Given exactly what a player's screen is given — a bearing rounded to
    a few degrees and one of three words for distance — and turned into a
    guess at a spot the same way a person would: over there, about that
    far. A bot handed the shouter's real coordinates would be a cheat
    wearing a name badge.

    Noises made by a seeker are ignored by hiders, since walking towards
    one is walking into the thing you are hiding from. Seekers
    investigate anything: that is what makes shouting cost something.
    """
    if bot["role"] is None:
        return

    if bot["role"] == "hider" and payload["role"] == "tagger":
        return

    brain = _brain(bot, now)

    cx, cy = _center(bot)
    reach = _NOISE_RANGE.get(payload["nearness"], _NOISE_RANGE["far"])

    brain["noise"] = (cx + math.cos(payload["bearing"]) * reach,
                      cy + math.sin(payload["bearing"]) * reach)
    brain["noise_at"] = now


def _fresh_noise(brain, now):
    """A noise still worth walking towards, or None."""
    if brain["noise"] is None:
        return None
    if now - brain["noise_at"] > _NOISE_LASTS:
        brain["noise"] = None
        return None
    return brain["noise"]


def _center(player):
    half = config.PLAYER_SIZE / 2
    return player["x"] + half, player["y"] + half


def _gap(a, b):
    ax, ay = _center(a)
    bx, by = _center(b)
    return math.hypot(ax - bx, ay - by)


def _gap_to(player, point):
    px, py = _center(player)
    return math.hypot(px - point[0], py - point[1])


# ---------------------------------------------------------------------------
# Deciding where to go
# ---------------------------------------------------------------------------

def _visible(room, bot, others):
    """Everyone this bot can actually see, by the same rule as a player.

    The whole difference between an opponent and a cheat.
    """
    return [other for other in others if game.can_see(room, bot, other)]


def _corner(point):
    """A centre, as the top-left a player record is stored by."""
    half = config.PLAYER_SIZE / 2
    return point[0] - half, point[1] - half


def _head_for(bot, brain, map_name, goal, purpose):
    """Plan a route to a point, given as a centre."""
    brain["path"] = maps.route(map_name, _center(bot), goal)
    brain["purpose"] = purpose


def _hiding_places(map_name, avoid_room):
    """Hiding spots worth using, with the ones by the base left out."""
    spots = []
    for index, spot in enumerate(maps.hiding_spots(map_name)):
        cx = spot["x"] + spot["w"] / 2
        cy = spot["y"] + spot["h"] / 2
        if avoid_room and maps.in_rect(avoid_room, cx, cy):
            continue
        spots.append((index, (cx, cy)))
    return spots


def _think_seeker(room, state, bot, brain, now):
    """Chase what you can see; otherwise search the house."""
    map_name = state["map"]
    home_room = maps.base_room(map_name)

    quarry = _visible(room, bot, [
        p for p in room["players"].values()
        if p is not bot and p["role"] == "hider" and p["in_game"]
        and p["state"] == "free"
    ])

    if quarry:
        target = min(quarry, key=lambda p: _gap(bot, p))
        _head_for(bot, brain, map_name, _center(target), "chase")
        return

    # Nothing in sight, but somebody made a noise. Going and looking is
    # the whole reason a shout is a risk.
    noise = _fresh_noise(brain, now)
    if noise is not None:
        if _gap_to(bot, noise) <= config.SEARCH_DISTANCE:
            brain["noise"] = None            # been there; nothing doing
        else:
            _head_for(bot, brain, map_name, noise, "noise")
            return

    # Nothing in sight, so work through the furniture. Nearest first,
    # which reads as somebody sweeping a house rather than teleporting
    # around it, and the base's room is left out because the round
    # punishes standing in it.
    places = _hiding_places(map_name, home_room)
    unsearched = [(i, p) for i, p in places if i not in brain["searched"]]

    if not unsearched:
        # Been everywhere. Start again — they have had time to move.
        brain["searched"] = set()
        unsearched = places

    if not unsearched:
        return

    # Stick with whatever we set out for. Re-picking the nearest every
    # third of a second means turning round halfway across a room the
    # moment something else edges ahead, which reads as dithering rather
    # than as searching.
    standing = brain.get("target")
    keeping = next((item for item in unsearched if item[0] == standing), None)

    index, spot = keeping or min(unsearched,
                                 key=lambda item: _gap_to(bot, item[1]))

    # Close enough to have looked in it.
    if _gap_to(bot, spot) <= config.SEARCH_DISTANCE * 0.7:
        brain["searched"].add(index)
        brain["target"] = None
        return

    brain["target"] = index
    _head_for(bot, brain, map_name, spot, "search")


def _think_hider(room, state, bot, brain, now):
    """Get out of sight, keep moving, and go home when your nerve goes."""
    map_name = state["map"]
    rules = game.rules_of(state)

    seekers = [
        p for p in room["players"].values()
        if p["role"] == "tagger" and p["in_game"]
    ]
    seen = _visible(room, bot, seekers)
    closest = min((_gap(bot, s) for s in seen), default=None)

    # Somebody is on top of us. Everything else can wait.
    if closest is not None and closest <= _ALARM:
        _head_for(bot, brain, map_name, _flee_to(map_name, bot, seen), "flee")
        brain["settle_until"] = 0.0
        return

    # A frozen team-mate we can reach is worth more than our own safety,
    # because the round cannot be won without them.
    if rules["rescues"]:
        frozen = [
            p for p in room["players"].values()
            if p is not bot and p["role"] == "hider" and p["in_game"]
            and p["state"] == "frozen"
        ]
        reachable = _visible(room, bot, frozen)
        if reachable:
            mate = min(reachable, key=lambda p: _gap(bot, p))
            _head_for(bot, brain, map_name, _center(mate), "rescue")
            return

        # Nothing visible, but somebody on our side called out. With a
        # wall between you and a frozen team-mate a shout is the only way
        # you would ever know they were there.
        noise = _fresh_noise(brain, now)
        if noise is not None:
            if _gap_to(bot, noise) <= config.RESCUE_DISTANCE * 2:
                brain["noise"] = None        # nobody here after all
            else:
                _head_for(bot, brain, map_name, noise, "rescue")
                return

    # Already home and safe: stay there. It is the winning square.
    if rules["home_is_safety"] and bot["state"] == "safe":
        brain["path"] = []
        brain["purpose"] = "home"
        return

    if state["phase"] == "counting":
        _head_for(bot, brain, map_name, _somewhere_to_hide(map_name, bot),
                  "hide")
        return

    # Their nerve decides when they stop hiding and run for it. Rolled
    # per bot, so a houseful of them does not all break at once.
    if rules["home_is_safety"] and game.round_progress(state) >= brain["nerve"]:
        _head_for(bot, brain, map_name, maps.base_center(map_name), "home")
        return

    # Otherwise: sit somewhere for a few seconds, then move on. A bot
    # that picked one wardrobe and stayed in it would be no fun at all,
    # and is exactly what people mean by a bush camper.
    #
    # The order of these three matters. Still walking beats settling, or
    # a bot that had just chosen somewhere would throw the route away a
    # third of a second later, on the next think, and get about a hundred
    # pixels per outing — which is how you write a bush camper by
    # accident.
    if brain["purpose"] == "hide" and brain["path"]:
        return

    if brain["purpose"] == "hide":
        # Arrived. The timer is for standing still, so it starts here
        # rather than when we set off.
        brain["settle_until"] = now + random.uniform(_SETTLE_MIN, _SETTLE_MAX)
        brain["purpose"] = "settled"
        return

    if now < brain["settle_until"]:
        brain["path"] = []
        brain["purpose"] = "settled"
        return

    _head_for(bot, brain, map_name, _somewhere_to_hide(map_name, bot), "hide")


def _somewhere_to_hide(map_name, bot):
    """The next hiding place: a proper distance off, but not the far end.

    Far enough that moving is actually moving — two cupboards in the same
    room is camping with extra steps — and near enough that a bot does
    not spend the whole round in transit. The nearer half of what is left
    after that, picked at random, so a houseful of them does not converge
    on the same three wardrobes.
    """
    home_room = maps.base_room(map_name)
    places = [p for _, p in _hiding_places(map_name, home_room)]
    here = _center(bot)
    here_room = maps.room_at(map_name, *here)

    def elsewhere(point):
        if math.dist(point, here) < _MOVE_AT_LEAST:
            return False
        return here_room is None or maps.room_at(map_name, *point) is not here_room

    options = [p for p in places if elsewhere(p)]
    if not options:
        # Cornered by the geometry rather than by anybody. Anywhere will
        # do, as long as it is somewhere else.
        options = [p for p in places if math.dist(p, here) > _ARRIVED * 2]
    if not options:
        return maps.random_standing_spot_center(map_name, avoid=home_room)

    options.sort(key=lambda p: math.dist(p, here))
    return random.choice(options[:max(3, len(options) // 2)])


def _flee_to(map_name, bot, seekers):
    """Somewhere further from the seekers than we are now.

    Picked from real standing places rather than by running along a
    vector, so a cornered bot heads for a door instead of into the wall
    behind it.
    """
    here = _center(bot)
    threats = [_center(s) for s in seekers]

    def clearance(point):
        return min(math.dist(point, threat) for threat in threats)

    now_clear = clearance(here)
    home_room = maps.base_room(map_name)

    options = [
        p for _, p in _hiding_places(map_name, home_room)
        if clearance(p) > now_clear + 120
    ]
    if options:
        # The nearest way out, not the furthest: running the length of
        # the house past a seeker is not an escape.
        return min(options, key=lambda p: math.dist(p, here))

    return maps.random_standing_spot_center(map_name, avoid=home_room)


# ---------------------------------------------------------------------------
# Moving
# ---------------------------------------------------------------------------

def _advance(bot, brain, state, dt, now):
    """Walk one step along the plan. Returns True if the bot moved."""
    while brain["path"] and _gap_to(bot, brain["path"][0]) <= _ARRIVED:
        brain["path"].pop(0)

    if not brain["path"]:
        return False

    cx, cy = _center(bot)
    goal = brain["path"][0]
    dx, dy = goal[0] - cx, goal[1] - cy
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return False

    running = brain["purpose"] in ("chase", "flee") and brain["sprint"] > 0.35
    if running:
        brain["sprint"] = max(0.0, brain["sprint"] - dt)
    else:
        brain["sprint"] = min(_SPRINT_SECONDS,
                              brain["sprint"] + dt * _SPRINT_SECONDS / _SPRINT_RECOVER)

    speed = config.PLAYER_SPEED * _PACE * (_SPRINT if running else 1.0)
    step = min(speed * dt, length)

    before = (bot["x"], bot["y"])
    bot["x"], bot["y"] = maps.walk(
        state["map"], bot["x"], bot["y"],
        dx / length * step, dy / length * step, config.PLAYER_SIZE,
    )

    # Which way they are pointing, for the modes where being looked at is
    # what matters.
    bot["facing"] = math.atan2(dy, dx)

    if math.dist(before, (bot["x"], bot["y"])) > step * 0.4:
        brain["progress_at"] = now
        brain["was"] = (bot["x"], bot["y"])
    elif now - brain["progress_at"] > _STUCK_SECONDS:
        # Wedged on something the route did not know about. Throw the
        # plan away; the next think picks another.
        brain["path"] = []
        brain["purpose"] = None
        brain["progress_at"] = now

    return before != (bot["x"], bot["y"])


# ---------------------------------------------------------------------------
# The tick
# ---------------------------------------------------------------------------

def step(code, dt, now):
    """Move a room's bots on by ``dt``. Returns ``(moved, shouted)``.

    ``moved`` is the bots whose position changed, for the caller to relay;
    ``shouted`` is the ones that called out, which is the only thing they
    say and the only way a frozen one gets found.
    """
    room = rooms.get(code)
    if room is None:
        return [], []

    state = game.state(code)
    if state is None or state["phase"] not in ("counting", "hunting"):
        return [], []

    moved = []
    shouted = []

    for bot in rooms.bots_in(room):
        if not bot["in_game"] or bot["role"] is None:
            continue

        brain = _brain(bot, now)

        if not game.can_move(room, bot):
            # Frozen, or held still. Calling for help is the one thing
            # still worth doing, and a frozen bot that could not would
            # simply never be found.
            if (bot["state"] == "frozen"
                    and now - brain["shouted_at"] >= _SHOUT_EVERY
                    and game.can_shout(room, bot, now)):
                game.mark_shouted(bot, now)
                brain["shouted_at"] = now
                shouted.append(bot)
            brain["path"] = []
            continue

        if now >= brain["think_at"] or not brain["path"]:
            brain["think_at"] = now + _THINK_SECONDS
            if bot["role"] == "tagger":
                _think_seeker(room, state, bot, brain, now)
            else:
                _think_hider(room, state, bot, brain, now)

        if _advance(bot, brain, state, dt, now):
            moved.append(bot)

    return moved, shouted
