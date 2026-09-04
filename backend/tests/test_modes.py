# -*- coding: utf-8 -*-
"""Game modes: the registry, choosing one, and when the choice is fixed.

The rules of a round come from a dict in modes.py rather than from
branches in game.py, so most of what is worth checking here is that the
dict is well formed and that the round picks it up at the right moment.
"""

import re

import game
import modes
import rooms


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

def test_every_mode_answers_every_question():
    """A mode missing a key would fail at the worst moment: mid-round.

    Defaults are merged in when the registry is built, so this is really
    a check that nothing was added straight to MODES by hand.
    """
    for mode_id, rules in modes.MODES.items():
        for key in ["id", "name", "blurb", "seekers", "on_tag", "rescues",
                    "hiding_conceals", "home_is_safety", "vision_radius",
                    "cone_degrees", "cone_reach", "round_seconds"]:
            assert key in rules, f"{mode_id} says nothing about {key}"

        assert rules["id"] == mode_id
        assert rules["seekers"] in ("one", "all_but_one")
        assert rules["on_tag"] in ("freeze", "convert", "recruit")
        assert rules["vision_radius"] > 0
        assert rules["round_seconds"] > 0


def test_the_default_mode_is_a_real_one():
    assert modes.DEFAULT_MODE in modes.MODES


def test_an_unknown_mode_falls_back_rather_than_exploding():
    """Mode ids arrive from clients, and a classic round beats a crash."""
    assert modes.get("no-such-mode")["id"] == modes.DEFAULT_MODE
    assert modes.get(None)["id"] == modes.DEFAULT_MODE
    assert not modes.is_mode("no-such-mode")


def test_the_listing_covers_every_mode_once():
    listed = [entry["id"] for entry in modes.listing()]
    assert listed == modes.ORDER
    assert sorted(listed) == sorted(modes.MODES)
    assert all(entry["blurb"] for entry in modes.listing())


# ---------------------------------------------------------------------------
# Choosing one
# ---------------------------------------------------------------------------

def test_a_new_room_starts_on_the_default_mode():
    code = rooms.create("Ann")
    assert rooms.public_view(code)["mode"] == modes.DEFAULT_MODE


def test_the_host_can_change_the_mode(client):
    code = rooms.create("Ann")
    target = next(m for m in modes.ORDER if m != modes.DEFAULT_MODE) \
        if len(modes.ORDER) > 1 else modes.DEFAULT_MODE

    ok, message = rooms.set_mode(code, target)
    assert ok, message
    assert rooms.public_view(code)["mode"] == target


def test_an_unknown_mode_is_refused():
    code = rooms.create("Ann")
    ok, message = rooms.set_mode(code, "definitely-not-a-mode")

    assert not ok
    assert message
    assert rooms.public_view(code)["mode"] == modes.DEFAULT_MODE


def test_only_the_host_may_change_the_mode(client):
    """The lobby hides the picker from everyone else, which is not the
    same as stopping them: the check has to be on the server."""
    code = rooms.create("Ann")
    rooms.add_player(code, "Bo")

    response = client.post("/set_mode",
                           json={"code": code, "name": "Bo",
                                 "mode": modes.DEFAULT_MODE})
    assert response.status_code == 403

    response = client.post("/set_mode",
                           json={"code": code, "name": "Ann",
                                 "mode": modes.DEFAULT_MODE})
    assert response.status_code == 200


def test_setting_a_mode_in_a_room_that_is_gone_is_not_an_error(client):
    response = client.post("/set_mode",
                           json={"code": "0000", "name": "Ann",
                                 "mode": modes.DEFAULT_MODE})
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# When the choice is fixed
# ---------------------------------------------------------------------------

def test_a_round_takes_a_copy_of_the_mode_when_it_starts():
    """Otherwise the host could rewrite the rules of a hunt in progress.

    Everyone would carry on playing to rules that had quietly changed
    underneath them, which is worse than not being able to change it.
    """
    other = [m for m in modes.ORDER if m != modes.DEFAULT_MODE]
    if not other:
        return

    code = rooms.create("Ann")
    rooms.add_player(code, "Bo")
    rooms.set_mode(code, other[0])

    ok, message = game.start(code)
    assert ok, message
    assert game.state(code)["mode"] == other[0]

    # The host fiddles with the lobby mid-round.
    rooms.set_mode(code, modes.DEFAULT_MODE)
    assert game.state(code)["mode"] == other[0]


def test_the_round_state_tells_clients_which_mode_they_are_in():
    code = rooms.create("Ann")
    rooms.add_player(code, "Bo")
    game.start(code)

    state = game.public_state(code)
    assert state["mode"] in modes.MODES
    assert state["modeName"] == modes.get(state["mode"])["name"]


# ---------------------------------------------------------------------------
# The lobby offers exactly what the server has
# ---------------------------------------------------------------------------

def test_the_lobby_offers_every_mode_and_no_others(client):
    """The picker is server-rendered, so this catches the template
    dropping the loop rather than the two lists drifting."""
    html = client.get("/room_page").get_data(as_text=True)
    offered = re.findall(r'class="mode" data-mode="([^"]+)"', html)

    assert offered == modes.ORDER

    for mode_id in modes.ORDER:
        assert modes.MODES[mode_id]["name"] in html


def test_the_hud_has_something_to_say_about_every_mode():
    """A mode with no copy would quietly tell people the classic thing.

    hud.js falls back to the classic lines for anything a mode does not
    override, which is the right behaviour at runtime and exactly why a
    missing entry would never show up as a crash — it would just tell a
    seeker in the wrong mode to freeze people who cannot be frozen.
    """
    import os

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "static", "js", "game", "hud.js"),
              encoding="utf-8") as handle:
        source = handle.read()

    block = re.search(r"const OBJECTIVES = \{(.*?)\n\};", source, re.S)
    assert block, "hud.js no longer has an OBJECTIVES table"

    # Top-level keys only: the phases nested inside are indented further.
    listed = re.findall(r"^\n?    ([a-z_]+): \{", block.group(1), re.M)

    assert sorted(listed) == sorted(modes.ORDER), (
        f"hud.js knows about {sorted(listed)}, "
        f"the server has {sorted(modes.ORDER)}"
    )


# ---------------------------------------------------------------------------
# Infection
# ---------------------------------------------------------------------------
#
# The tagged join the hunt instead of freezing, so the round accelerates:
# these check that a tag moves a player between the two sides, and that
# the win conditions follow them across.

import config  # noqa: E402
import maps  # noqa: E402
import pytest  # noqa: E402

from test_game import BASE, cast, clock, hunting, put  # noqa: E402,F401


def infecting(clock, *names):
    """A room mid-hunt, playing Infection."""
    code = rooms.create(names[0])
    for name in names[1:]:
        rooms.add_player(code, name)
    for name in names:
        rooms.enter_game(f"sid-{name}", code, name, "house1")

    rooms.set_mode(code, "infection")

    ok, message = game.start(code)
    assert ok, message
    assert game.state(code)["mode"] == "infection"

    game.resolve(code, force=True)              # gathering -> counting
    clock(config.COUNTDOWN_SECONDS + 1)
    game.resolve(code, force=True)              # counting -> hunting
    assert game.state(code)["phase"] == "hunting"

    clock(config.RELOCATE_PIN_SECONDS + 0.1)    # past the relocation pin
    return code


def test_a_tagged_hider_becomes_a_seeker_rather_than_freezing(clock):
    code = infecting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    caught, safe = hiders
    put(safe, 2200, 1500)                       # far away, still hiding
    put(caught, 900, 900)
    put(seeker, 900, 900)                       # right on top of them

    game.resolve(code, force=True)

    assert caught["role"] == "tagger"
    assert caught["state"] == "free", "an infected player is not frozen"
    assert game.state(code)["phase"] == "hunting", "one hider is still out"


def test_an_infected_player_can_tag_for_themselves(clock):
    """The point of the mode: the second seeker has to actually hunt."""
    code = infecting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    turned, last = hiders
    put(last, 2200, 1500)
    put(turned, 900, 900)
    put(seeker, 900, 900)
    game.resolve(code, force=True)
    assert turned["role"] == "tagger"

    # The original seeker wanders off; the newly turned one does the work.
    put(seeker, 300, 300)
    put(turned, 2200, 1500)
    game.resolve(code, force=True)

    assert last["role"] == "tagger"
    assert game.state(code)["winner"] == "tagger"


def test_the_seekers_win_once_nobody_is_left_hiding(clock):
    code = infecting(clock, "Alice", "Bob")
    seeker, hiders = cast(code)

    put(hiders[0], 900, 900)
    put(seeker, 900, 900)
    game.resolve(code, force=True)

    state = game.state(code)
    assert state["phase"] == "over"
    assert state["winner"] == "tagger"
    # Everybody was caught, so this is a win rather than an abandoned round.
    assert state["note"] is None


def test_infected_players_do_not_end_the_round_by_reaching_home(clock):
    """Home is for hiders. Somebody who changed sides walking over the
    base must not be counted as having escaped."""
    code = infecting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    turned, last = hiders
    put(last, 2200, 1500)
    put(turned, 900, 900)
    put(seeker, 900, 900)
    game.resolve(code, force=True)
    assert turned["role"] == "tagger"

    put(turned, *BASE)
    game.resolve(code, force=True)

    assert turned["state"] == "free", "a seeker cannot be 'safe'"
    assert game.state(code)["phase"] == "hunting"


def test_hiders_still_win_by_getting_the_survivors_home(clock):
    code = infecting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(seeker, 300, 300)
    for hider in hiders:
        put(hider, *BASE)

    game.resolve(code, force=True)
    assert game.state(code)["winner"] == "hiders"


def test_nobody_is_thawed_in_a_mode_with_nothing_frozen(clock):
    """Rescues are switched off, and there is nothing to rescue anyway."""
    assert modes.get("infection")["rescues"] is False

    code = infecting(clock, "Alice", "Bob", "Carol")
    _, hiders = cast(code)

    for hider in hiders:
        assert hider["state"] == "free"


def test_a_conversion_asks_for_sight_lines_to_be_redrawn(clock):
    """Changing sides changes who you can see and who can see you, and no
    position update need arrive to make that true."""
    code = infecting(clock, "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(hiders[1], 2200, 1500)
    put(hiders[0], 900, 900)
    put(seeker, 900, 900)

    assert "sight" in game.resolve(code, force=True)


# ---------------------------------------------------------------------------
# Juggernaut
# ---------------------------------------------------------------------------
#
# A chase rather than a search: furniture hides nobody, a tag is final,
# and the only thing worth doing is running for the base.

def playing(clock, mode, *names):
    """A room mid-hunt, in ``mode``."""
    code = rooms.create(names[0])
    for name in names[1:]:
        rooms.add_player(code, name)
    for name in names:
        rooms.enter_game(f"sid-{name}", code, name, "house1")

    ok, message = rooms.set_mode(code, mode)
    assert ok, message

    ok, message = game.start(code)
    assert ok, message

    game.resolve(code, force=True)              # gathering -> counting
    clock(config.COUNTDOWN_SECONDS + 1)
    game.resolve(code, force=True)              # counting -> hunting
    assert game.state(code)["phase"] == "hunting"

    clock(config.RELOCATE_PIN_SECONDS + 0.1)    # past the relocation pin
    return code


# Far enough that the seeker is plainly not searching the furniture, near
# enough that they can still see that far in this mode.
WATCHING_FROM = 280


def _seeker_watching_the_wardrobe(clock, mode):
    """A hider tucked in the wardrobe, with the seeker across the room."""
    from test_game import hiding_spot

    code = playing(clock, mode, "Alice", "Bob")
    seeker, hiders = cast(code)

    spot_x, spot_y = hiding_spot("wardrobe")
    put(hiders[0], spot_x, spot_y)
    put(seeker, spot_x - WATCHING_FROM, spot_y)

    return rooms.get(code), seeker, hiders[0]


def test_furniture_hides_nobody_from_the_seeker(clock):
    """The whole point of the mode: the wardrobe is only a wardrobe."""
    assert config.SEARCH_DISTANCE < WATCHING_FROM
    assert WATCHING_FROM < modes.get("juggernaut")["vision_radius"]

    room, seeker, hider = _seeker_watching_the_wardrobe(clock, "juggernaut")
    assert game.can_see(room, seeker, hider)


def test_the_same_hider_would_be_concealed_in_classic(clock):
    """The mirror of the test above, so it is checking the mode rather
    than an accident of where these two happen to be standing."""
    room, seeker, hider = _seeker_watching_the_wardrobe(clock, "classic")
    assert not game.can_see(room, seeker, hider)


def test_a_caught_player_stays_caught(clock):
    """No rescues: standing over a frozen team-mate does nothing."""
    code = playing(clock, "juggernaut", "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    caught, friend = hiders
    put(caught, 900, 900)
    put(seeker, 900, 900)
    put(friend, 2200, 1500)
    game.resolve(code, force=True)
    assert caught["state"] == "frozen"

    # A friend stands with them for far longer than a thaw would take.
    put(seeker, 300, 300)
    put(friend, 900, 900)
    game.resolve(code, force=True)
    clock(config.RESCUE_HOLD_SECONDS * 3)
    game.resolve(code, force=True)

    assert caught["state"] == "frozen", "nobody should have been thawed"
    assert caught["rescue_since"] is None


def test_the_clock_is_shorter_than_classic():
    """A pure chase is tiring rather than tense if it runs on."""
    assert (modes.get("juggernaut")["round_seconds"]
            < modes.get("classic")["round_seconds"])


def test_reaching_home_still_wins_it(clock):
    code = playing(clock, "juggernaut", "Alice", "Bob", "Carol")
    seeker, hiders = cast(code)

    put(seeker, 300, 300)
    for hider in hiders:
        put(hider, *BASE)

    game.resolve(code, force=True)
    assert game.state(code)["winner"] == "hiders"


def test_the_client_is_told_this_mode_hides_nobody(clock):
    """The renderer stops drawing a search ring and the HUD stops saying
    "hidden" off the back of this, so it has to actually be sent."""
    code = playing(clock, "juggernaut", "Alice", "Bob")
    rules = game.public_state(code)["rules"]

    assert rules["hidingConceals"] is False
    assert rules["visionRadius"] == modes.get("juggernaut")["vision_radius"]


# ---------------------------------------------------------------------------
# Blackout
# ---------------------------------------------------------------------------
#
# Everybody sees about a room's worth. The seeker trades that for a torch
# that reaches much further but only points where they last moved, so the
# thing worth checking is that it can be stepped around.

import math  # noqa: E402


def _looking_east(clock, mode="blackout"):
    """A seeker facing +x, and a hider to place around them."""
    code = playing(clock, mode, "Alice", "Bob")
    seeker, hiders = cast(code)

    put(seeker, 1300, 850)
    seeker["facing"] = 0.0                      # straight along +x

    return rooms.get(code), seeker, hiders[0]


def _place_at(player, seeker, bearing, distance):
    """Put ``player`` ``distance`` away from ``seeker``, at ``bearing``."""
    half = config.PLAYER_SIZE / 2
    cx, cy = seeker["x"] + half, seeker["y"] + half
    put(player, cx + math.cos(bearing) * distance,
        cy + math.sin(bearing) * distance)


def test_the_seeker_sees_a_long_way_down_the_beam(clock):
    room, seeker, hider = _looking_east(clock)
    rules = modes.get("blackout")

    # Further than anybody's all-round sight, and well inside the torch.
    reach = rules["vision_radius"] + 100
    assert reach < rules["cone_reach"]

    _place_at(hider, seeker, 0.0, reach)
    assert game.can_see(room, seeker, hider)


def test_the_seeker_cannot_see_someone_stood_behind_them(clock):
    """The whole reason for a cone: a torch can be walked around."""
    room, seeker, hider = _looking_east(clock)

    # Close enough that a circle of sight would show them easily.
    _place_at(hider, seeker, math.pi, modes.get("blackout")["vision_radius"] - 40)
    assert not game.can_see(room, seeker, hider)


def test_the_same_player_is_seen_once_the_seeker_turns_round(clock):
    """Pairs with the test above, so it is the facing being checked and
    not something else about that patch of floor."""
    room, seeker, hider = _looking_east(clock)
    _place_at(hider, seeker, math.pi, modes.get("blackout")["vision_radius"] - 40)

    seeker["facing"] = math.pi                  # turn to look at them
    assert game.can_see(room, seeker, hider)


def test_somebody_at_arms_length_is_seen_whichever_way_you_face(clock):
    """A hider invisible while stood on the seeker's toes would read as a
    bug, and they are close enough to be tagged anyway."""
    room, seeker, hider = _looking_east(clock)

    _place_at(hider, seeker, math.pi, config.TAG_DISTANCE)
    assert game.can_see(room, seeker, hider)


def test_the_beam_does_not_reach_forever(clock):
    room, seeker, hider = _looking_east(clock)

    _place_at(hider, seeker, 0.0, modes.get("blackout")["cone_reach"] + 60)
    assert not game.can_see(room, seeker, hider)


def test_hiders_keep_their_sight_all_round(clock):
    """The cone is the seeker's trade, not a rule about everybody."""
    room, seeker, hider = _looking_east(clock)

    _place_at(seeker, hider, math.pi, 120)
    hider["facing"] = 0.0                       # looking the other way
    assert game.can_see(room, hider, seeker)


def test_everyone_sees_less_than_they_would_in_the_light(clock):
    assert (modes.get("blackout")["vision_radius"]
            < modes.get("classic")["vision_radius"])


def test_the_hunt_is_longer_because_the_dark_is_slower(clock):
    assert (modes.get("blackout")["round_seconds"]
            > modes.get("classic")["round_seconds"])


def test_facing_arrives_from_the_client_and_is_kept(clock):
    """The cone is only worth anything if the angle is actually current."""
    code = playing(clock, "blackout", "Alice", "Bob")
    seeker, _ = cast(code)

    rooms.move(seeker["sid"], 900.0, 900.0, math.pi / 2)
    assert seeker["facing"] == pytest.approx(math.pi / 2)

    # A client that keeps counting turns instead of wrapping must not
    # hand us an angle that grows without bound.
    rooms.move(seeker["sid"], 900.0, 900.0, math.pi / 2 + 8 * math.pi)
    assert seeker["facing"] == pytest.approx(math.pi / 2)


def test_a_move_without_a_facing_keeps_the_last_one(clock):
    """Every other mode's client has no reason to send one."""
    code = playing(clock, "blackout", "Alice", "Bob")
    seeker, _ = cast(code)

    rooms.move(seeker["sid"], 900.0, 900.0, math.pi)
    rooms.move(seeker["sid"], 950.0, 900.0)

    assert seeker["facing"] == pytest.approx(math.pi)


# ---------------------------------------------------------------------------
# Sardines
# ---------------------------------------------------------------------------
#
# The inverted one: one player hides, everybody else looks, and finding
# them puts you on their side. The round is really deciding who was last
# to work out where everyone went.

def test_one_player_hides_and_everybody_else_seeks(clock):
    code = playing(clock, "sardines", "Alice", "Bob", "Carol")

    roles = sorted(p["role"] for p in rooms.get(code)["players"].values())
    assert roles == ["hider", "tagger", "tagger"]


def test_the_room_counts_while_the_one_hiding_runs(clock):
    """The count is inverted with the roles: it is the seekers who are
    blind and rooted, and the lone hider who gets to move."""
    code = rooms.create("Alice")
    for name in ["Bob", "Carol"]:
        rooms.add_player(code, name)
    for name in ["Alice", "Bob", "Carol"]:
        rooms.enter_game(f"sid-{name}", code, name, "house1")

    rooms.set_mode(code, "sardines")
    game.start(code)
    game.resolve(code, force=True)
    assert game.state(code)["phase"] == "counting"

    room = rooms.get(code)
    hider = next(p for p in room["players"].values() if p["role"] == "hider")
    seekers = [p for p in room["players"].values() if p["role"] == "tagger"]

    assert game.can_move(room, hider), "the one hiding has to get away"
    for seeker in seekers:
        assert not game.can_move(room, seeker), "everybody else is counting"
        assert not game.can_see(room, seeker, hider), "eyes shut"


def test_finding_them_puts_you_on_their_side(clock):
    code = playing(clock, "sardines", "Alice", "Bob", "Carol")
    room = rooms.get(code)

    hider = next(p for p in room["players"].values() if p["role"] == "hider")
    finder, straggler = [p for p in room["players"].values()
                         if p["role"] == "tagger"]

    put(hider, 900, 900)
    put(finder, 900, 900)
    put(straggler, 2300, 1500)

    game.resolve(code, force=True)

    assert finder["role"] == "hider", "the finder joins them, not the reverse"
    assert hider["role"] == "hider", "the one hiding does not change"
    assert straggler["role"] == "tagger"


def test_the_last_one_still_looking_loses(clock):
    code = playing(clock, "sardines", "Alice", "Bob", "Carol")
    room = rooms.get(code)

    hider = next(p for p in room["players"].values() if p["role"] == "hider")
    finder, straggler = [p for p in room["players"].values()
                         if p["role"] == "tagger"]

    put(hider, 900, 900)
    put(finder, 900, 900)
    put(straggler, 2300, 1500)

    game.resolve(code, force=True)

    state = game.state(code)
    assert state["phase"] == "over"
    assert straggler["name"] in state["note"], "the loser is named"


def test_with_only_two_players_it_ends_when_they_are_found(clock):
    """Waiting for one seeker to be left would end the round before it
    started: there is only ever one of them."""
    code = playing(clock, "sardines", "Alice", "Bob")
    room = rooms.get(code)

    hider = next(p for p in room["players"].values() if p["role"] == "hider")
    seeker = next(p for p in room["players"].values() if p["role"] == "tagger")

    game.resolve(code, force=True)
    assert game.state(code)["phase"] == "hunting", "not over before it began"

    put(hider, 900, 900)
    put(seeker, 900, 900)
    game.resolve(code, force=True)

    assert game.state(code)["phase"] == "over"
    assert game.state(code)["note"] is None, "nobody was last; everyone found them"


def test_hiding_well_enough_runs_the_clock_out(clock):
    code = playing(clock, "sardines", "Alice", "Bob", "Carol")
    room = rooms.get(code)

    hider = next(p for p in room["players"].values() if p["role"] == "hider")
    put(hider, 2400, 100)
    for seeker in [p for p in room["players"].values() if p["role"] == "tagger"]:
        put(seeker, 200, 1600)

    clock(modes.get("sardines")["round_seconds"] + 1)
    game.resolve(code, force=True)

    state = game.state(code)
    assert state["phase"] == "over"
    assert state["winner"] == "hiders"
    assert "hid too well" in state["note"]


def test_the_base_is_just_a_rug(clock):
    """No running home: standing on the base must not take a player out
    of a round that ends by everybody being found."""
    code = playing(clock, "sardines", "Alice", "Bob", "Carol")
    room = rooms.get(code)

    hider = next(p for p in room["players"].values() if p["role"] == "hider")
    put(hider, *BASE)
    for seeker in [p for p in room["players"].values() if p["role"] == "tagger"]:
        put(seeker, 200, 1600)

    game.resolve(code, force=True)

    assert hider["state"] == "free", "nobody is 'safe' in this one"
    assert game.state(code)["phase"] == "hunting"


def test_the_hiding_place_still_conceals_the_pile(clock):
    """Somebody who has squeezed in is hidden from whoever is still
    looking, exactly as the original hider is — otherwise the first find
    would give the rest of them away."""
    from test_game import hiding_spot

    # Four, so that one person finding them leaves two still looking and
    # the round is not over before there is anything to check.
    code = playing(clock, "sardines", "Alice", "Bob", "Carol", "Dan")
    room = rooms.get(code)

    hider = next(p for p in room["players"].values() if p["role"] == "hider")
    finder, straggler, other = [p for p in room["players"].values()
                                if p["role"] == "tagger"]

    spot = hiding_spot("wardrobe")
    put(hider, *spot)
    put(finder, *spot)
    put(straggler, 2300, 1500)
    put(other, 200, 1600)

    game.resolve(code, force=True)
    assert finder["role"] == "hider"
    assert game.state(code)["phase"] == "hunting", "two are still looking"

    # A straggler walks up, but not close enough to search the wardrobe.
    put(straggler, spot[0] - 250, spot[1])
    assert not game.can_see(room, straggler, hider)
    assert not game.can_see(room, straggler, finder), \
        "the first find must not give away the rest of the pile"


def test_the_client_is_told_who_was_singled_out(clock):
    """The HUD names them, and in this mode they are the hider rather
    than the seeker, so "tagger" alone is not enough to go on."""
    code = playing(clock, "sardines", "Alice", "Bob", "Carol")
    room = rooms.get(code)

    hider = next(p for p in room["players"].values() if p["role"] == "hider")
    state = game.public_state(code)

    assert state["chosen"] == hider["name"]
    assert state["tagger"] is None, "there is no single seeker in this one"
    assert state["rules"]["homeIsSafety"] is False
