# -*- coding: utf-8 -*-
"""Bots: adding them, and whether they actually play.

A bot is a player record with nobody behind it, so most of what is worth
checking here is that the rest of the game cannot tell the difference —
they are dealt roles, they can be tagged and thawed, they count towards
winning — and that the two things which *are* different are right: they
move themselves, and nothing is ever sent to them.

The behaviour tests run a whole round with a wound-on clock. They are
deliberately loose: asserting a bot ends up in a particular wardrobe
would be asserting the random number generator, and the thing worth
knowing is that it went somewhere, kept going somewhere, and played by
the same sight rules as everybody else.
"""

import math

import bots
import config
import game
import maps
import modes
import rooms

# The same hand-wound clock the round tests use, so a 20 second count
# does not take 20 seconds and a whole round takes milliseconds.
from test_game import clock  # noqa: F401

BASE = maps.base_center("house1")


def with_bots(clock, count, *humans):
    """A room of ``humans`` and ``count`` bots, mid-hunt."""
    code = rooms.create(humans[0])
    for name in humans[1:]:
        rooms.add_player(code, name)
    for name in humans:
        rooms.enter_game(f"sid-{name}", code, name, "house1")

    for _ in range(count):
        ok, message = bots.add(code)
        assert ok, message

    ok, message = game.start(code)
    assert ok, message

    game.resolve(code, force=True)              # gathering -> counting
    clock(config.COUNTDOWN_SECONDS + 1)
    game.resolve(code, force=True)              # counting -> hunting
    clock(config.RELOCATE_PIN_SECONDS + 0.1)
    game.take_relocated(code)

    return code


def run(code, clock, seconds, step=0.1):
    """Play a room forward, driving the bots the way the tick does."""
    room = rooms.get(code)

    for _ in range(int(seconds / step)):
        now = clock(step)
        moved, shouted = bots.step(code, step, now)

        for bot in shouted:
            for listener, payload in game.earshot(room, bot):
                if listener["is_bot"]:
                    bots.hear(listener, payload, now)

        game.resolve(code, force=True)
        if game.state(code)["phase"] == "over":
            break


def the_bots(code):
    return rooms.bots_in(rooms.get(code))


# ---------------------------------------------------------------------------
# Adding and removing
# ---------------------------------------------------------------------------

def test_a_bot_joins_the_room_and_the_world_at_once():
    """There is nobody to press "join", and a bot that had to be waited
    for would hold the count up for everybody."""
    code = rooms.create("Ann")
    ok, message = bots.add(code)
    assert ok, message

    bot = the_bots(code)[0]
    assert bot["in_game"]
    assert bot["is_bot"]
    assert not bot["isHost"]


def test_bots_are_named_apart_from_each_other_and_from_people():
    code = rooms.create("Robin")            # takes the first bot name
    for _ in range(4):
        assert bots.add(code)[0]

    names = [p["name"] for p in rooms.get(code)["players"].values()]
    assert len(names) == len(set(names))
    assert "Robin" in names


def test_there_is_a_ceiling_on_them():
    code = rooms.create("Ann")
    for _ in range(bots.MAX_BOTS):
        assert bots.add(code)[0]

    ok, message = bots.add(code)
    assert not ok and message
    assert len(the_bots(code)) == bots.MAX_BOTS


def test_a_bot_can_be_taken_out_again():
    code = rooms.create("Ann")
    bots.add(code)
    bots.add(code)

    ok, message = bots.remove_one(code)
    assert ok, message
    assert len(the_bots(code)) == 1

    bots.remove_one(code)
    assert not bots.remove_one(code)[0], "nothing left to remove"


def test_a_bot_never_becomes_the_host():
    """Somebody has to be able to press start, and it cannot be them."""
    code = rooms.create("Ann")
    bots.add(code)
    rooms.add_player(code, "Bo")

    del rooms.get(code)["players"]["ann"]       # the host walks out
    room = rooms.get(code)

    assert room["players"]["bo"]["isHost"]
    assert not any(p["isHost"] for p in rooms.bots_in(room))


def test_a_bot_does_not_expire_the_way_a_lost_connection_does():
    """It has no connection to lose."""
    import time

    code = rooms.create("Ann")
    bots.add(code)

    rooms.get(code)["players"]["ann"]["left_at"] = \
        time.monotonic() - config.DISCONNECT_GRACE_SECONDS - 1

    room = rooms.get(code)
    assert room is not None, "the bot kept the room alive, which is right"
    assert len(rooms.bots_in(room)) == 1


def test_a_bot_makes_a_one_player_room_playable():
    code = rooms.create("Ann")
    assert not game.start(code)[0], "one person is not a game"

    bots.add(code)
    assert game.start(code)[0]


# ---------------------------------------------------------------------------
# They are dealt into the round like anybody else
# ---------------------------------------------------------------------------

def test_bots_are_given_roles(clock):
    code = with_bots(clock, 3, "Ann")

    for bot in the_bots(code):
        assert bot["role"] in ("hider", "tagger")


def test_a_bot_can_be_the_seeker(clock):
    """Not guaranteed in any one round, so this asks for several."""
    seen = set()
    for _ in range(25):
        rooms.reset()
        code = with_bots(clock, 3, "Ann")
        seeker = next(p for p in rooms.get(code)["players"].values()
                      if p["role"] == "tagger")
        seen.add(seeker["is_bot"])

    assert seen == {True, False}, f"only ever {seen}"


def test_a_bot_hider_counts_towards_the_hiders_winning(clock):
    code = with_bots(clock, 1, "Ann", "Bo")
    room = rooms.get(code)

    hiders = [p for p in room["players"].values() if p["role"] == "hider"]
    seeker = next(p for p in room["players"].values() if p["role"] == "tagger")

    half = config.PLAYER_SIZE / 2
    seeker["x"], seeker["y"] = 2200, 1400
    for hider in hiders:
        hider["x"], hider["y"] = BASE[0] - half, BASE[1] - half

    game.resolve(code, force=True)
    assert game.state(code)["winner"] == "hiders"


def test_a_bot_can_be_tagged_and_thawed(clock):
    code = with_bots(clock, 2, "Ann")
    room = rooms.get(code)

    seeker = next(p for p in room["players"].values() if p["role"] == "tagger")
    hiders = [p for p in room["players"].values() if p["role"] == "hider"]
    victim, friend = hiders[0], hiders[1]

    half = config.PLAYER_SIZE / 2
    victim["x"], victim["y"] = 300 - half, 300 - half
    seeker["x"], seeker["y"] = 320 - half, 300 - half
    friend["x"], friend["y"] = 2200, 1400

    game.resolve(code, force=True)
    assert victim["state"] == "frozen"

    seeker["x"], seeker["y"] = 2200, 1400
    friend["x"], friend["y"] = 320 - half, 300 - half
    game.resolve(code, force=True)
    assert victim["state"] == "free"


# ---------------------------------------------------------------------------
# They actually play
# ---------------------------------------------------------------------------

def test_a_bot_leaves_where_it_started(clock):
    code = with_bots(clock, 2, "Ann")
    was = {b["name"]: (b["x"], b["y"]) for b in the_bots(code)}

    run(code, clock, 6)

    moved = [b for b in the_bots(code) if (b["x"], b["y"]) != was[b["name"]]]
    assert moved, "nobody went anywhere"


def a_hider_and_a_distant_seeker(clock):
    """One bot hiding, with the seeker parked at the far end of the house.

    Left alone on purpose: fleeing and being frozen are their own
    behaviours, and both would muddy a test about what a bot does when
    nothing is happening to it.

    A second hider is parked out of the way as well, so that the bot
    wandering over the base cannot end the round by being the last one
    home — which would stop the clock, stop the bots, and quietly turn
    this into a test of nothing at all.
    """
    code = with_bots(clock, 1, "Ann", "Bo")
    room = rooms.get(code)

    bot = the_bots(code)[0]
    bot["role"] = "hider"
    bot["state"] = "free"
    bot["x"], bot["y"] = 300, 300               # well clear of the base

    seeker, spare = (p for p in room["players"].values() if p is not bot)
    seeker["role"] = "tagger"
    seeker["x"], seeker["y"] = 2400, 1560
    spare["role"] = "hider"
    spare["state"] = "free"
    spare["x"], spare["y"] = 2400, 100

    return code, bot


def test_a_bot_does_not_pick_one_spot_and_sit_in_it(clock):
    """The whole complaint about bad hide-and-seek bots: they find a bush
    and stay in it, and the round becomes a search of the whole map."""
    code, bot = a_hider_and_a_distant_seeker(clock)

    seen = set()
    for _ in range(40):
        run(code, clock, 1)
        room = maps.room_at("house1", bot["x"] + 20, bot["y"] + 20)
        if room:
            seen.add(room["name"])

    assert len(seen) > 1, f"forty seconds and it never left {seen}"


def test_a_bot_finishes_the_journey_it_set_out_on(clock):
    """It used to plan a route and throw it away a third of a second
    later, on the next think, because the "stay put for a bit" timer
    started when it set off rather than when it arrived. The result was
    about a hundred pixels per outing — a bush camper written by
    accident, and invisible unless you measured the distance.
    """
    code, bot = a_hider_and_a_distant_seeker(clock)

    was = (bot["x"], bot["y"])
    furthest = 0.0
    for _ in range(120):
        run(code, clock, 0.1)
        furthest = max(furthest, math.dist(was, (bot["x"], bot["y"])))

    assert furthest > bots._MOVE_AT_LEAST * 0.8, \
        f"only got {furthest:.0f}px from where it started in twelve seconds"


def test_a_bot_never_walks_through_a_wall(clock):
    code = with_bots(clock, 3, "Ann")
    half = config.PLAYER_SIZE / 2

    for _ in range(30):
        run(code, clock, 1)
        for bot in the_bots(code):
            box = {"x": bot["x"], "y": bot["y"],
                   "w": config.PLAYER_SIZE, "h": config.PLAYER_SIZE}
            for wall in maps.load("house1")["walls"]:
                assert not maps._overlaps(box, wall), \
                    f'{bot["name"]} is inside a wall at {box}'
            assert 0 <= bot["x"] <= 2600 - half
            assert 0 <= bot["y"] <= 1700 - half


def test_a_bot_seeker_does_not_camp_the_hall(clock):
    """The round would move them on anyway, so a bot that had to be
    evicted every five seconds would just look broken.

    Measured as a share of the time rather than by where they happen to
    be at the end: the hall is the middle of the house and crossing it is
    how you get anywhere, so being in it is fine and living in it is not.
    """
    hall = maps.base_room("house1")
    inside = 0
    samples = 0

    for _ in range(5):
        rooms.reset()
        code = with_bots(clock, 3, "Ann")
        seeker = next((p for p in rooms.get(code)["players"].values()
                       if p["role"] == "tagger" and p["is_bot"]), None)
        if seeker is None:
            continue

        for _ in range(60):
            run(code, clock, 0.5)
            samples += 1
            inside += maps.in_rect(hall, seeker["x"] + 20, seeker["y"] + 20)

    if not samples:
        return

    assert inside / samples < 0.35, \
        f"a bot seeker spent {inside / samples:.0%} of the round in the hall"


def test_a_bot_seeker_finds_somebody_eventually(clock):
    """Loose on purpose. It is not asking the bot to be good, only to be
    doing the thing rather than wandering."""
    caught = 0

    for _ in range(6):
        rooms.reset()
        code = with_bots(clock, 4, "Ann")
        run(code, clock, modes.get("classic")["round_seconds"])

        room = rooms.get(code)
        caught += sum(1 for p in room["players"].values()
                      if p["role"] == "hider" and p["state"] == "frozen")
        caught += sum(1 for p in room["players"].values()
                      if p["role"] == "tagger" and p["is_bot"] is False)

    assert caught > 0, "six full rounds and nobody was ever caught"


def test_a_frozen_bot_calls_for_help(clock):
    code = with_bots(clock, 2, "Ann")
    room = rooms.get(code)

    frozen = next((b for b in the_bots(code) if b["role"] == "hider"), None)
    if frozen is None:
        return

    frozen["state"] = "frozen"
    frozen["x"], frozen["y"] = 300, 300

    shouts = 0
    for _ in range(200):
        now = clock(0.1)
        shouts += len(bots.step(code, 0.1, now)[1])

    assert shouts > 0, "a frozen bot nobody can see never said anything"


def test_a_bot_walks_towards_a_noise_it_heard(clock):
    """It is given the same rounded bearing a player's screen is given,
    which is the difference between an opponent and a cheat."""
    code = with_bots(clock, 1, "Ann")
    bot = the_bots(code)[0]
    bot["role"] = "hider"
    bot["x"], bot["y"] = 300, 300

    now = clock(0)
    bots._brain(bot, now)
    bots.hear(bot, {"role": "hider", "state": "frozen",
                    "bearing": 0.0, "nearness": "nearby"}, now)

    guess = bot["brain"]["noise"]
    assert guess is not None
    # Due east of them, since that is the bearing they were handed.
    assert guess[0] > bot["x"] + 200
    assert abs(guess[1] - (bot["y"] + 20)) < 1


def test_a_hider_ignores_a_noise_the_seeker_made(clock):
    """Walking towards it is walking into the thing you are hiding from."""
    code = with_bots(clock, 1, "Ann")
    bot = the_bots(code)[0]
    bot["role"] = "hider"

    now = clock(0)
    bots._brain(bot, now)
    bots.hear(bot, {"role": "tagger", "state": "free",
                    "bearing": 0.0, "nearness": "close"}, now)

    assert bot["brain"]["noise"] is None


def test_a_bot_is_told_no_more_than_a_player_would_be(clock):
    """A bot chases what it can see, and can_see is the same function the
    server uses to decide what to send a human. Standing on the far side
    of a wall from one has to be as good as standing on the far side of a
    wall from anybody."""
    code = with_bots(clock, 1, "Ann")
    room = rooms.get(code)
    bot = the_bots(code)[0]
    human = room["players"]["ann"]

    half = config.PLAYER_SIZE / 2
    # Either side of the living room / kitchen wall, above the doorway.
    bot["x"], bot["y"] = 560 - half, 200 - half
    human["x"], human["y"] = 760 - half, 200 - half

    assert not game.can_see(room, bot, human)
    assert math.dist((560, 200), (760, 200)) < config.VISION_RADIUS
