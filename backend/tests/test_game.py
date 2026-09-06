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


# ---------------------------------------------------------------------------
# Who is it
# ---------------------------------------------------------------------------
#
# Being the seeker used to be something that happened to you. Asking for
# it beats the rotation; nobody asking is an even draw.

def test_a_volunteer_gets_the_job(clock):
    code = make_room("Alice", "Bob", "Carol")
    rooms.set_volunteer(code, "Carol", True)

    for _ in range(12):
        ok, message = game.start(code)
        assert ok, message
        assert game.state(code)["tagger"] == "carol"


def test_the_draw_is_between_the_volunteers_when_there_are_several(clock):
    code = make_room("Alice", "Bob", "Carol")
    rooms.set_volunteer(code, "Bob", True)
    rooms.set_volunteer(code, "Carol", True)

    picked = set()
    for _ in range(40):
        game.start(code)
        picked.add(game.state(code)["tagger"])

    assert picked <= {"bob", "carol"}, "somebody who never asked was picked"


def test_asking_beats_the_rotation(clock):
    """Somebody volunteering two rounds running is asking, not being
    landed with it, so the "not twice in a row" rule gives way."""
    code = make_room("Alice", "Bob")
    rooms.set_volunteer(code, "Bob", True)

    game.start(code)
    assert game.state(code)["tagger"] == "bob"

    game.state(code)["last_tagger"] = "bob"
    game.start(code)
    assert game.state(code)["tagger"] == "bob"


def test_taking_your_hand_down_puts_you_back_in_the_crowd(clock):
    code = make_room("Alice", "Bob", "Carol")
    rooms.set_volunteer(code, "Carol", True)
    rooms.set_volunteer(code, "Carol", False)

    picked = set()
    for _ in range(40):
        game.start(code)
        game.state(code)["last_tagger"] = None
        picked.add(game.state(code)["tagger"])

    assert len(picked) > 1, "the draw closed around one player"


def test_with_nobody_asking_everybody_is_in_the_draw(clock):
    code = make_room("Alice", "Bob", "Carol")

    picked = set()
    for _ in range(60):
        game.start(code)
        # Clear the rotation each time, or the previous seeker is held
        # back and this would only ever be testing that.
        game.state(code)["last_tagger"] = None
        picked.add(game.state(code)["tagger"])

    assert picked == {"alice", "bob", "carol"}


def test_a_removed_player_is_not_in_the_draw(clock):
    code = make_room("Alice", "Bob", "Carol")
    ok, message = rooms.remove_player(code, "Carol")
    assert ok, message

    for _ in range(20):
        game.start(code)
        assert game.state(code)["tagger"] in ("alice", "bob")


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
# The base is a wall to the seeker
# ---------------------------------------------------------------------------
#
# Parking on the base would decide the round by standing on the finish
# line, so it is the one patch of floor the seeker does not get.

def on_base(player):
    """A position whose whole box sits inside the base zone."""
    half = config.PLAYER_SIZE / 2
    return BASE[0] - half, BASE[1] - half


def test_the_seeker_cannot_stand_on_the_base(clock):
    code = hunting(clock, "Alice", "Bob")
    room = rooms.get(code)
    seeker, hiders = cast(code)

    put(seeker, BASE[0] - 300, BASE[1])
    assert not game.can_stand(room, seeker, *on_base(seeker))


def test_hiders_are_not_stopped_by_it(clock):
    """It is their finish line; walking onto it is the point."""
    code = hunting(clock, "Alice", "Bob")
    room = rooms.get(code)
    _, hiders = cast(code)

    assert game.can_stand(room, hiders[0], *on_base(hiders[0]))


def test_the_seeker_may_walk_right_up_to_the_edge(clock):
    """A wall, not an exclusion zone. Waiting outside the door is fair."""
    code = hunting(clock, "Alice", "Bob")
    room = rooms.get(code)
    seeker, _ = cast(code)

    zone = maps.base_zones(config.DEFAULT_MAP)[0]
    beside = (zone["x"] - config.PLAYER_SIZE - 1, zone["y"])

    put(seeker, BASE[0] - 300, BASE[1])
    assert game.can_stand(room, seeker, *beside)


def test_a_seeker_somehow_inside_it_can_get_out_again(clock):
    """Self-healing on purpose: a stuck player is worse than a lost rule."""
    code = hunting(clock, "Alice", "Bob")
    room = rooms.get(code)
    seeker, _ = cast(code)

    seeker["x"], seeker["y"] = on_base(seeker)
    assert game.can_stand(room, seeker, BASE[0] - 300, BASE[1])


def test_nothing_is_walled_off_before_the_hunt_starts(clock):
    """Everybody starts on the base, seeker included."""
    code = started("Alice", "Bob")
    room = rooms.get(code)
    seeker, _ = cast(code)

    assert game.can_stand(room, seeker, *on_base(seeker))


def test_the_base_is_open_to_everyone_in_sardines(clock):
    """There is nothing to run home to, so there is nothing to defend."""
    import modes

    code = make_room("Alice", "Bob")
    rooms.set_mode(code, "sardines")
    game.start(code)
    game.resolve(code, force=True)
    clock(config.COUNTDOWN_SECONDS + 1)
    game.resolve(code, force=True)

    room = rooms.get(code)
    assert modes.get("sardines")["home_is_safety"] is False
    for player in room["players"].values():
        assert game.can_stand(room, player, *on_base(player))


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


def test_running_into_a_frozen_hider_frees_them(clock):
    """No hold: contact is the whole rescue.

    Standing still beside somebody for a second and a half looked exactly
    like standing still doing nothing, so people gave up a beat before it
    landed. The cost of a rescue is the trip, not the wait.
    """
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)
    frozen, rescuer = hiders

    put(seeker, 2200, 1400)
    put(frozen, 300, 300)
    frozen["state"] = "frozen"
    put(rescuer, 300 + config.RESCUE_DISTANCE - 10, 300)

    game.resolve(code, force=True)
    assert frozen["state"] == "free"


def test_walking_past_out_of_reach_is_not_a_rescue(clock):
    """It is still contact, so somebody in the next room does nothing."""
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)
    frozen, rescuer = hiders

    put(seeker, 2200, 1400)
    put(frozen, 300, 300)
    frozen["state"] = "frozen"
    put(rescuer, 300 + config.RESCUE_DISTANCE + 20, 300)

    game.resolve(code, force=True)
    assert frozen["state"] == "frozen"


def test_a_hider_stood_on_the_base_cannot_thaw_anybody(clock):
    """You do not get to be safe and useful at the same time.

    Reaching out of the base to free somebody just past its edge would
    make a rescue free, and the seeker could never close a round out.
    """
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)
    frozen, safe = hiders

    zone = maps.base_zones(config.DEFAULT_MAP)[0]
    inside = (zone["x"] + zone["w"] / 2, zone["y"] + zone["h"] - 5)
    just_outside = (inside[0], zone["y"] + zone["h"] + 45)
    assert (just_outside[1] - inside[1]) < config.RESCUE_DISTANCE

    put(seeker, 2200, 1400)
    put(frozen, *just_outside)
    frozen["state"] = "frozen"
    put(safe, *inside)

    game.resolve(code, force=True)
    assert safe["state"] == "safe", "they are stood on the base"
    assert frozen["state"] == "frozen"


def test_the_seeker_cannot_thaw_anybody(clock):
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(hiders[0], 300, 300)
    hiders[0]["state"] = "frozen"
    put(hiders[1], 2200, 1400)
    put(seeker, 320, 300)                   # standing over their catch

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


def test_a_hider_on_the_base_cannot_be_tagged(clock):
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(hiders[0], *BASE)
    put(hiders[1], 300, 300)
    game.resolve(code, force=True)
    assert hiders[0]["state"] == "safe"

    put(seeker, BASE[0] + 5, BASE[1])
    game.resolve(code, force=True)
    assert hiders[0]["state"] == "safe"


def test_stepping_off_the_base_makes_you_fair_game_again(clock):
    """Safety is a place, not a prize. Touching home once used to buy
    immunity for the rest of the round, and people strolled back out
    through the middle of a hunt untouchable."""
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(seeker, 2200, 1400)
    put(hiders[1], 300, 300)

    put(hiders[0], *BASE)
    game.resolve(code, force=True)
    assert hiders[0]["state"] == "safe"

    put(hiders[0], BASE[0] + 400, BASE[1])
    game.resolve(code, force=True)
    assert hiders[0]["state"] == "free"


def test_a_hider_who_wandered_back_out_can_be_caught(clock):
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(seeker, 2200, 1400)
    put(hiders[1], 300, 300)

    put(hiders[0], *BASE)
    game.resolve(code, force=True)
    assert hiders[0]["state"] == "safe"

    # Out of the base, and the seeker is right there.
    put(hiders[0], 300, 300)
    put(seeker, 320, 300)
    game.resolve(code, force=True)
    assert hiders[0]["state"] == "frozen"


def test_a_frozen_hider_is_not_saved_by_where_they_are_standing(clock):
    """Somebody tagged on the doorstep stays tagged."""
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(seeker, 2200, 1400)
    put(hiders[1], 300, 300)
    put(hiders[0], *BASE)
    hiders[0]["state"] = "frozen"

    game.resolve(code, force=True)
    assert hiders[0]["state"] == "frozen"


def test_hiders_win_by_all_being_on_the_base_at_once(clock):
    """The flip side of safety being a place: the round is won by
    everybody standing on it together, not by each of them having been
    there at some point."""
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(seeker, 2200, 1400)
    put(hiders[0], *BASE)
    put(hiders[1], 300, 300)
    game.resolve(code, force=True)
    assert game.state(code)["phase"] == "hunting"

    put(hiders[1], BASE[0] + 30, BASE[1])
    game.resolve(code, force=True)
    assert game.state(code)["winner"] == "hiders"


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


def test_one_player_home_does_not_end_it_for_everybody_else(clock):
    """The bug this replaces: a round that stopped mid-play.

    One hider on the base and the rest still running is a position, not a
    result. It ends when they are all frozen, all home, or out of time —
    nothing else.
    """
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(seeker, 2200, 1400)
    put(hiders[0], *BASE)
    put(hiders[1], 300, 300)

    game.resolve(code, force=True)
    assert hiders[0]["state"] == "safe"
    assert game.state(code)["phase"] == "hunting"


def test_one_home_and_one_frozen_plays_on_to_the_clock(clock):
    """Nobody free is left, but the round still has time on it.

    The clock is what decides this one, not the server deciding for the
    room that there is nothing left to watch.
    """
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(seeker, 2200, 1400)
    put(hiders[0], *BASE)
    hiders[1]["state"] = "frozen"
    put(hiders[1], 300, 300)

    game.resolve(code, force=True)
    assert game.state(code)["phase"] == "hunting"

    clock(config.ROUND_SECONDS + 1)
    game.resolve(code, force=True)

    state = game.state(code)
    assert state["phase"] == "over"
    assert state["winner"] == "tagger"


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


def test_a_dropped_connection_does_not_end_the_round_on_the_spot(clock):
    """A phone locking for a second is not the same as leaving.

    This used to hand the round to whoever was left, which is how a game
    could end while two people were still running around in it.
    """
    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(seeker, 2200, 1400)
    put(hiders[0], *BASE)
    hiders[1]["sid"] = None                 # lost their connection

    game.resolve(code, force=True)
    assert game.state(code)["phase"] == "hunting"


def test_a_hider_who_really_left_stops_holding_the_round_open(clock):
    """The other half of it: rooms.py drops them once the grace period is
    up, and the round resolves the moment it does."""
    import time

    code = hunting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(seeker, 2200, 1400)
    put(hiders[0], *BASE)
    hiders[1]["sid"] = None
    hiders[1]["left_at"] = time.monotonic() - config.DISCONNECT_GRACE_SECONDS - 1

    game.resolve(code, force=True)
    state = game.state(code)
    assert state["phase"] == "over"
    assert state["winner"] == "hiders"


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


# Both ends inside the living room (x 48-640, y 48-726), so this is the
# distance rule being tested and not the wall rule.
LOUNGE_X = 300


def test_nobody_is_visible_beyond_the_vision_radius(clock):
    code = hunting(clock, "Alice", "Bob")
    room = rooms.get(code)
    seeker, hiders = cast(code)

    put(seeker, LOUNGE_X, 150)
    put(hiders[0], LOUNGE_X, 150 + config.VISION_RADIUS + 40)
    assert not game.can_see(room, seeker, hiders[0])

    put(hiders[0], LOUNGE_X, 150 + config.VISION_RADIUS - 40)
    assert game.can_see(room, seeker, hiders[0])


def test_nobody_is_visible_through_a_wall(clock):
    """The house used to be see-through: from the study you could watch
    the seeker cross the kitchen, which made the rooms decoration and
    distance the only real hiding place."""
    code = hunting(clock, "Alice", "Bob")
    room = rooms.get(code)
    seeker, hiders = cast(code)

    # Either side of the living room / kitchen wall, well within sight.
    put(seeker, 560, 200)
    put(hiders[0], 760, 200)
    assert _distance_between(seeker, hiders[0]) < config.VISION_RADIUS
    assert not game.can_see(room, seeker, hiders[0])


def test_a_doorway_is_a_hole_you_can_see_through(clock):
    """The pair to the test above, so it is the wall being checked and
    not simply that patch of the house."""
    code = hunting(clock, "Alice", "Bob")
    room = rooms.get(code)
    seeker, hiders = cast(code)

    # Level with the doorway between the two rooms rather than the wall.
    put(seeker, 560, 360)
    put(hiders[0], 760, 360)
    assert game.can_see(room, seeker, hiders[0])


def _distance_between(a, b):
    half = config.PLAYER_SIZE / 2
    return ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5


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
    assert state["tally"] == {"hiders": 2, "free": 1, "frozen": 0, "safe": 1,
                              "seekers": 1}
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
