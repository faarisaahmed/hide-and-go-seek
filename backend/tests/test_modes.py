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
