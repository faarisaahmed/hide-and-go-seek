# -*- coding: utf-8 -*-
"""The round: roles, phases, tagging, thawing, and who wins.

Everything here goes through game.py directly rather than over a socket,
so the rules can be checked without also standing up a client. The
socket-level view of the same rules — chiefly that hidden players are
never sent to the seeker — lives in test_events.py.
"""

import pytest

import config
import game
import maps
import rooms

BASE = maps.base_center("house1")


@pytest.fixture
def clock(monkeypatch):
    """A hand-wound clock, so a 20 second count does not take 20 seconds."""
    held = {"now": 1000.0}
    monkeypatch.setattr(game, "_now", lambda: held["now"])

    def advance(seconds=0.0):
        held["now"] += seconds
        return held["now"]

    return advance


def make_room(*names):
    code = rooms.create(names[0])
    for name in names[1:]:
        rooms.add_player(code, name)
    for name in names:
        rooms.enter_game(f"sid-{name}", code, name, "house1")
    return code


def started(*names):
    """A room with everybody in the world and a round just begun."""
    code = make_room(*names)
    ok, message = game.start(code)
    assert ok, message
    return code


def hunting(clock, *names):
    """Fast-forward a fresh round to the moment the seeker opens their eyes."""
    code = started(*names)

    game.resolve(code, force=True)          # gathering -> counting
    clock(config.COUNTDOWN_SECONDS + 1)
    game.resolve(code, force=True)          # counting -> hunting

    assert game.state(code)["phase"] == "hunting"

    # Everyone started on the base, so everyone was just relocated and is
    # briefly pinned. Step past that, as a real second of play would.
    clock(config.RELOCATE_PIN_SECONDS + 0.1)
    return code


def cast(code):
    """``(seeker, [hiders])`` for a room."""
    players = rooms.get(code)["players"].values()
    seeker = next(p for p in players if p["role"] == "tagger")
    return seeker, [p for p in players if p["role"] == "hider"]


def put(player, x, y):
    """Place a player by their centre, which is how distances are measured."""
    half = config.PLAYER_SIZE / 2
    player["x"], player["y"] = x - half, y - half
def hiding_spot(label, corner=False):
    """A hiding spot by name, as a centre — or as a top-left corner.

    Looked up by label rather than by coordinate, so rearranging the
    furniture does not quietly turn these tests into tests of an empty
    patch of floor.
    """
    spot = next(s for s in maps.hiding_spots(config.DEFAULT_MAP)
                if s["label"] == label)
    cx = spot["x"] + spot["w"] / 2
    cy = spot["y"] + spot["h"] / 2

    if corner:
        half = config.PLAYER_SIZE / 2
        return cx - half, cy - half
    return cx, cy


# ---------------------------------------------------------------------------
# Starting
# ---------------------------------------------------------------------------

def test_a_round_needs_someone_to_seek(clock):
    code = make_room("Alice")
    ok, message = game.start(code)
    assert not ok and "at least 2" in message


def test_starting_picks_one_seeker_and_makes_everybody_else_a_hider(clock):
    code = started("Alice", "Bob", "Carol")

    roles = sorted(p["role"] for p in rooms.get(code)["players"].values())
    assert roles == ["hider", "hider", "tagger"]


def test_everybody_starts_on_the_base(clock):
    code = started("Alice", "Bob", "Carol")

    for player in rooms.get(code)["players"].values():
        half = config.PLAYER_SIZE / 2
        away = ((player["x"] + half - BASE[0]) ** 2
                + (player["y"] + half - BASE[1]) ** 2) ** 0.5
        assert away < 200, f"{player['name']} did not start at the base"


def test_the_seeker_changes_between_rounds(clock):
    code = started("Alice", "Bob")
    first = game.state(code)["tagger"]

    game.resolve(code, force=True)                  # -> counting
    clock(config.COUNTDOWN_SECONDS + 1)
    game.resolve(code, force=True)                  # -> hunting
    clock(config.ROUND_SECONDS + 1)
    game.resolve(code, force=True)                  # -> over
    assert game.state(code)["phase"] == "over"

    ok, _ = game.start(code)
    assert ok
    # With two players there is exactly one other candidate, so this is
    # not luck.
    assert game.state(code)["tagger"] != first


def test_a_new_round_puts_everyone_back_on_the_base(clock):
    """Including a round the host restarts mid-hunt, which is allowed."""
    code = hunting(clock, "Alice", "Bob")
    seeker, hiders = cast(code)
    put(hiders[0], 200, 200)

    game.start(code)
    half = config.PLAYER_SIZE / 2
    away = ((hiders[0]["x"] + half - BASE[0]) ** 2
            + (hiders[0]["y"] + half - BASE[1]) ** 2) ** 0.5
    assert away < 200


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------

def test_the_count_starts_once_everybody_has_loaded_in(clock):
    code = started("Alice", "Bob")
    assert game.state(code)["phase"] == "gathering"

    assert "phase" in game.resolve(code, force=True)
    assert game.state(code)["phase"] == "counting"


def test_a_player_who_never_loads_in_does_not_hold_up_the_count(clock):
    code = started("Alice", "Bob")
    # Bob's client never reached the game page.
    rooms.get(code)["players"]["bob"]["in_game"] = False

    game.resolve(code, force=True)
    assert game.state(code)["phase"] == "gathering"

    clock(config.GATHER_SECONDS + 1)
    game.resolve(code, force=True)
    assert game.state(code)["phase"] == "counting"


def test_the_hunt_starts_when_the_count_runs_out(clock):
    code = started("Alice", "Bob")
    game.resolve(code, force=True)

    clock(config.COUNTDOWN_SECONDS - 1)
    game.resolve(code, force=True)
    assert game.state(code)["phase"] == "counting"

    clock(2)
    game.resolve(code, force=True)
    assert game.state(code)["phase"] == "hunting"


def test_a_room_with_no_round_is_left_alone(clock):
    code = make_room("Alice", "Bob")
    assert game.resolve(code, force=True) == set()
    assert game.state(code)["phase"] == "lobby"


# ---------------------------------------------------------------------------
# Who may move
# ---------------------------------------------------------------------------

def test_the_seeker_cannot_move_while_counting(clock):
    code = started("Alice", "Bob")
    game.resolve(code, force=True)

    room = rooms.get(code)
    seeker, hiders = cast(code)

    assert not game.can_move(room, seeker)
    assert game.can_move(room, hiders[0])


def test_nobody_moves_while_the_room_is_still_loading_in(clock):
    code = started("Alice", "Bob")
    room = rooms.get(code)

    for player in room["players"].values():
        assert not game.can_move(room, player)


def test_a_frozen_hider_cannot_move(clock):
    code = hunting(clock, "Alice", "Bob")
    room = rooms.get(code)
    _, hiders = cast(code)

    assert game.can_move(room, hiders[0])
    hiders[0]["state"] = "frozen"
    assert not game.can_move(room, hiders[0])


def test_wandering_is_allowed_with_no_round_running(clock):
    """Opening the game page on its own should not be a dead screen."""
    code = make_room("Alice", "Bob")
    room = rooms.get(code)
    assert game.can_move(room, room["players"]["alice"])


# ---------------------------------------------------------------------------
# Nobody hides next to the base
# ---------------------------------------------------------------------------

def test_hiders_loitering_by_the_base_are_moved_out_when_the_count_ends(clock):
    code = started("Alice", "Bob")
    game.resolve(code, force=True)

    seeker, hiders = cast(code)
    lurker = hiders[0]
    put(lurker, BASE[0] + 60, BASE[1])      # right next to home

    clock(config.COUNTDOWN_SECONDS + 1)
    game.resolve(code, force=True)

    half = config.PLAYER_SIZE / 2
    away = ((lurker["x"] + half - BASE[0]) ** 2
            + (lurker["y"] + half - BASE[1]) ** 2) ** 0.5
    assert away >= config.NO_HIDE_RADIUS

    # And they were put somewhere worth being, not just shoved outside
    # the circle.
    assert maps.hiding_spot_at("house1", lurker["x"] + half, lurker["y"] + half)


def test_a_relocated_hider_is_pinned_long_enough_to_hear_about_it(clock):
    """Their client has updates in flight claiming the old spot.

    Accepting one would put them straight back beside the base, quietly
    undoing the rule that had just moved them.
    """
    code = started("Alice", "Bob")
    game.resolve(code, force=True)

    _, hiders = cast(code)
    lurker = hiders[0]
    put(lurker, BASE[0] + 60, BASE[1])

    clock(config.COUNTDOWN_SECONDS + 1)
    game.resolve(code, force=True)

    room = rooms.get(code)
    assert not game.can_move(room, lurker)

    clock(config.RELOCATE_PIN_SECONDS + 0.1)
    assert game.can_move(room, lurker)


def test_relocated_hiders_are_handed_over_to_be_told_where_they_are(clock):
    code = started("Alice", "Bob")
    game.resolve(code, force=True)
    clock(config.COUNTDOWN_SECONDS + 1)

    assert "moved" in game.resolve(code, force=True)

    moved = game.take_relocated(code)
    assert [p["name"] for p in moved] == [cast(code)[1][0]["name"]]
    # Draining is one-shot, or the same correction goes out every tick.
    assert game.take_relocated(code) == []


def test_a_hider_who_actually_hid_is_not_pinned(clock):
    code = started("Alice", "Bob")
    game.resolve(code, force=True)

    _, hiders = cast(code)
    put(hiders[0], 300, 300)

    clock(config.COUNTDOWN_SECONDS + 1)
    assert "moved" not in game.resolve(code, force=True)
    assert game.can_move(rooms.get(code), hiders[0])


def test_a_hider_who_actually_hid_is_left_where_they_are(clock):
    code = started("Alice", "Bob")
    game.resolve(code, force=True)

    _, hiders = cast(code)
    put(hiders[0], 300, 300)
    before = (hiders[0]["x"], hiders[0]["y"])

    clock(config.COUNTDOWN_SECONDS + 1)
    game.resolve(code, force=True)

    assert (hiders[0]["x"], hiders[0]["y"]) == before


def test_the_seeker_is_not_moved_off_the_base(clock):
    code = started("Alice", "Bob")
    game.resolve(code, force=True)

    seeker, _ = cast(code)
    before = (seeker["x"], seeker["y"])

    clock(config.COUNTDOWN_SECONDS + 1)
    game.resolve(code, force=True)

    assert (seeker["x"], seeker["y"]) == before


# ---------------------------------------------------------------------------
# Tagging and thawing
# ---------------------------------------------------------------------------

def test_touching_a_hider_freezes_them(clock):
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(seeker, 300, 300)
    put(hiders[0], 300 + config.TAG_DISTANCE - 2, 300)
    put(hiders[1], 2000, 1400)

    assert "players" in game.resolve(code, force=True)
    assert hiders[0]["state"] == "frozen"
    assert hiders[1]["state"] == "free"


def test_a_near_miss_is_not_a_tag(clock):
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(seeker, 300, 300)
    put(hiders[0], 300 + config.TAG_DISTANCE + 5, 300)
    put(hiders[1], 2000, 1400)

    game.resolve(code, force=True)
    assert hiders[0]["state"] == "free"


def test_a_free_hider_thaws_a_frozen_one_after_holding_position(clock):
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)
    frozen, rescuer = hiders

    put(seeker, 2200, 1400)
    put(frozen, 300, 300)
    frozen["state"] = "frozen"
    put(rescuer, 300 + config.RESCUE_DISTANCE - 10, 300)

    game.resolve(code, force=True)
    assert frozen["state"] == "frozen", "a rescue should take a moment"

    clock(config.RESCUE_HOLD_SECONDS + 0.1)
    game.resolve(code, force=True)
    assert frozen["state"] == "free"


def test_stepping_away_mid_rescue_starts_the_hold_again(clock):
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)
    frozen, rescuer = hiders

    put(seeker, 2200, 1400)
    put(frozen, 300, 300)
    frozen["state"] = "frozen"
    put(rescuer, 320, 300)

    clock(config.RESCUE_HOLD_SECONDS - 0.2)
    game.resolve(code, force=True)

    put(rescuer, 1000, 1000)                # scared off
    game.resolve(code, force=True)
    assert frozen["rescue_since"] is None

    put(rescuer, 320, 300)
    game.resolve(code, force=True)
    clock(0.4)
    game.resolve(code, force=True)
    assert frozen["state"] == "frozen", "the hold should have restarted"


def test_a_hider_who_is_already_home_cannot_thaw_anybody(clock):
    """Otherwise rescuing costs nothing and the seeker can never win."""
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)
    frozen, safe = hiders

    put(seeker, 2200, 1400)
    put(frozen, 300, 300)
    frozen["state"] = "frozen"
    put(safe, 320, 300)
    safe["state"] = "safe"

    clock(config.RESCUE_HOLD_SECONDS + 1)
    game.resolve(code, force=True)
    assert frozen["state"] == "frozen"


def test_the_seeker_cannot_thaw_anybody(clock):
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(hiders[0], 300, 300)
    hiders[0]["state"] = "frozen"
    put(hiders[1], 2200, 1400)
    put(seeker, 320, 300)                   # standing over their catch

    clock(config.RESCUE_HOLD_SECONDS + 1)
    game.resolve(code, force=True)
    assert hiders[0]["state"] == "frozen"


# ---------------------------------------------------------------------------
# Getting home
# ---------------------------------------------------------------------------

def test_reaching_the_base_makes_a_hider_safe(clock):
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(seeker, 2200, 1400)
    put(hiders[0], *BASE)
    put(hiders[1], 300, 300)

    game.resolve(code, force=True)
    assert hiders[0]["state"] == "safe"


def test_reaching_the_base_beats_a_tag_in_the_same_moment(clock):
    """A dive for the door should be worth trying."""
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(hiders[0], *BASE)
    put(seeker, BASE[0] + 5, BASE[1])       # right on top of them
    put(hiders[1], 300, 300)

    game.resolve(code, force=True)
    assert hiders[0]["state"] == "safe"


def test_a_safe_hider_cannot_be_tagged_afterwards(clock):
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(hiders[0], *BASE)
    put(hiders[1], 300, 300)
    game.resolve(code, force=True)
    assert hiders[0]["state"] == "safe"

    put(seeker, BASE[0] + 5, BASE[1])
    game.resolve(code, force=True)
    assert hiders[0]["state"] == "safe"


# ---------------------------------------------------------------------------
# Winning
# ---------------------------------------------------------------------------

def test_hiders_win_when_every_one_of_them_gets_home(clock):
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(seeker, 2200, 1400)
    for hider in hiders:
        put(hider, *BASE)

    game.resolve(code, force=True)
    state = game.state(code)
    assert state["phase"] == "over"
    assert state["winner"] == "hiders"


def test_the_seeker_wins_by_freezing_everybody(clock):
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(seeker, 300, 300)
    for hider in hiders:
        put(hider, 320, 300)

    game.resolve(code, force=True)
    state = game.state(code)
    assert state["phase"] == "over"
    assert state["winner"] == "tagger"


def test_one_frozen_hider_costs_the_hiders_the_round(clock):
    """A round ends when nobody free is left to change the outcome."""
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(seeker, 2200, 1400)
    put(hiders[0], *BASE)
    hiders[1]["state"] = "frozen"
    put(hiders[1], 300, 300)

    game.resolve(code, force=True)
    assert game.state(code)["winner"] == "tagger"


def test_running_out_of_time_goes_to_the_seeker(clock):
    code = hunting(clock, "Alice", "Bob")
    seeker, hiders = cast(code)

    put(seeker, 2200, 1400)
    put(hiders[0], 300, 300)

    clock(config.ROUND_SECONDS + 1)
    game.resolve(code, force=True)

    state = game.state(code)
    assert state["winner"] == "tagger"
    assert state["note"] == "Time ran out."


def test_the_round_ends_if_the_seeker_leaves(clock):
    code = hunting(clock, "Alice", "Bob")
    seeker, _ = cast(code)

    del rooms.get(code)["players"][seeker["name"].lower()]
    game.resolve(code, force=True)

    state = game.state(code)
    assert state["phase"] == "over"
    assert state["winner"] is None
    assert "seeker left" in state["note"]


def test_a_hider_whose_phone_dropped_does_not_stall_the_round(clock):
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(seeker, 2200, 1400)
    put(hiders[0], *BASE)
    hiders[1]["sid"] = None                 # lost their connection

    game.resolve(code, force=True)
    assert game.state(code)["phase"] == "over"


# ---------------------------------------------------------------------------
# Who can see whom
# ---------------------------------------------------------------------------

def test_the_seeker_sees_nothing_while_counting(clock):
    code = started("Alice", "Bob")
    game.resolve(code, force=True)

    room = rooms.get(code)
    seeker, hiders = cast(code)
    put(seeker, 300, 300)
    put(hiders[0], 320, 300)                # standing right beside them

    assert not game.can_see(room, seeker, hiders[0])
    # The hider can still see the seeker: they are watching them count.
    assert game.can_see(room, hiders[0], seeker)


def test_nobody_is_visible_beyond_the_vision_radius(clock):
    code = hunting(clock, "Alice", "Bob")
    room = rooms.get(code)
    seeker, hiders = cast(code)

    put(seeker, 300, 300)
    put(hiders[0], 300 + config.VISION_RADIUS + 40, 300)
    assert not game.can_see(room, seeker, hiders[0])

    put(hiders[0], 300 + config.VISION_RADIUS - 40, 300)
    assert game.can_see(room, seeker, hiders[0])


def test_a_hider_in_the_furniture_is_invisible_until_the_seeker_searches_it(clock):
    code = hunting(clock, "Alice", "Bob")
    room = rooms.get(code)
    seeker, hiders = cast(code)

    spot = hiding_spot("under the bed")
    put(hiders[0], *spot)

    # In plain sight by distance, but tucked away.
    put(seeker, spot[0] + config.VISION_RADIUS - 40, spot[1])
    assert not game.can_see(room, seeker, hiders[0])

    put(seeker, spot[0] + config.SEARCH_DISTANCE - 10, spot[1])
    assert game.can_see(room, seeker, hiders[0])


def test_hiders_can_see_each_other_hiding(clock):
    """Rescues would be impossible if hiding hid you from your own side."""
    code = hunting(clock, "Alice", "Bob", "Carol")
    room = rooms.get(code)
    _, hiders = cast(code)

    spot = hiding_spot("under the bed")
    put(hiders[0], *spot)
    put(hiders[1], spot[0] + 200, spot[1])

    assert game.can_see(room, hiders[1], hiders[0])


def test_a_frozen_hider_cannot_be_concealed_by_furniture(clock):
    """They have to be findable, or nobody can come and thaw them."""
    code = hunting(clock, "Alice", "Bob")
    room = rooms.get(code)
    seeker, hiders = cast(code)

    spot = hiding_spot("under the bed")
    put(hiders[0], *spot)
    hiders[0]["state"] = "frozen"
    put(seeker, spot[0] + config.VISION_RADIUS - 40, spot[1])

    assert game.can_see(room, seeker, hiders[0])


def test_the_end_of_a_round_reveals_everyone(clock):
    code = hunting(clock, "Alice", "Bob")
    room = rooms.get(code)
    seeker, hiders = cast(code)

    put(seeker, 300, 300)
    put(hiders[0], 2200, 1400)
    assert not game.can_see(room, seeker, hiders[0])

    clock(config.ROUND_SECONDS + 1)
    game.resolve(code, force=True)
    assert game.can_see(room, seeker, hiders[0])


# ---------------------------------------------------------------------------
# What clients are told
# ---------------------------------------------------------------------------

def test_public_state_reports_the_round_without_leaking_positions(clock):
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)
    put(seeker, 2200, 1400)
    put(hiders[0], *BASE)
    game.resolve(code, force=True)

    state = game.public_state(code)
    assert state["phase"] == "hunting"
    assert state["tagger"] == seeker["name"]
    assert state["tally"] == {"hiders": 2, "free": 1, "frozen": 0, "safe": 1}
    assert state["roundSecondsLeft"] <= config.ROUND_SECONDS

    for player in state["players"]:
        assert set(player) == {
            "name", "emoji", "role", "state", "isHost", "connected", "inGame",
        }


def test_public_state_counts_down_the_current_phase(clock):
    code = started("Alice", "Bob")
    game.resolve(code, force=True)
    assert game.public_state(code)["secondsLeft"] == config.COUNTDOWN_SECONDS

    clock(5)
    assert game.public_state(code)["secondsLeft"] == config.COUNTDOWN_SECONDS - 5


def test_resetting_clears_the_round(clock):
    code = hunting(clock, "Alice", "Bob")
    game.reset(code)

    state = game.state(code)
    assert state["phase"] == "lobby" and state["tagger"] is None
    for player in rooms.get(code)["players"].values():
        assert player["role"] is None
        assert player["state"] == "free"


def test_state_for_a_room_that_never_existed(clock):
    assert game.state("0000") is None
    assert game.public_state("0000") is None
    assert game.resolve("0000") == set()
    assert game.start("0000") == (False, "Room not found")
