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
                    "cone_degrees", "round_seconds"]:
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
