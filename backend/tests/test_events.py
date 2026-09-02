# -*- coding: utf-8 -*-
"""Socket.IO protocol, including the lobby-to-game handover."""

import config
import game
import maps
import rooms
from conftest import events, payloads


def room_with(client, *names):
    code = client.post("/create_room", json={"name": names[0]}).get_json()["room_code"]
    for name in names[1:]:
        client.post("/join_room", json={"code": code, "name": name})
    return code


# ---------------------------------------------------------------------------
# Lobby
# ---------------------------------------------------------------------------

def test_join_lobby_returns_the_room(client, sock):
    code = room_with(client, "Alice")
    a = sock()
    a.emit("join_lobby", {"code": code, "name": "Alice"})

    room = payloads(a, "room_updated")[0]
    assert [p["name"] for p in room["players"]] == ["Alice"]


def test_join_lobby_for_an_unknown_room_is_rejected(client, sock):
    a = sock()
    a.emit("join_lobby", {"code": "0000", "name": "Alice"})
    assert events(a, "join_rejected")


def test_join_lobby_by_someone_not_in_the_room_is_rejected(client, sock):
    code = room_with(client, "Alice")
    a = sock()
    a.emit("join_lobby", {"code": code, "name": "Mallory"})
    assert events(a, "join_rejected")


def test_a_new_player_is_pushed_to_the_lobby(client, sock):
    code = room_with(client, "Alice")
    a = sock()
    a.emit("join_lobby", {"code": code, "name": "Alice"})
    a.get_received()

    client.post("/join_room", json={"code": code, "name": "Bob"})

    room = payloads(a, "room_updated")[-1]
    assert [p["name"] for p in room["players"]] == ["Alice", "Bob"]


def test_chat_and_emoji_are_pushed_to_the_lobby(client, sock):
    code = room_with(client, "Alice")
    a = sock()
    a.emit("join_lobby", {"code": code, "name": "Alice"})
    a.get_received()

    client.post("/send_chat", json={"code": code, "name": "Alice", "message": "hi"})
    assert payloads(a, "room_updated")[-1]["chat"] == [{"name": "Alice", "message": "hi"}]

    client.post("/change_emoji",
                json={"code": code, "name": "Alice", "emoji": config.EMOJI_POOL[-1]})
    assert payloads(a, "room_updated")[-1]["players"][0]["emoji"] == config.EMOJI_POOL[-1]


# ---------------------------------------------------------------------------
# Starting the game
# ---------------------------------------------------------------------------

def test_host_can_start_the_game(client, sock):
    code = room_with(client, "Alice", "Bob")
    a, b = sock(), sock()
    a.emit("join_lobby", {"code": code, "name": "Alice"})
    b.emit("join_lobby", {"code": code, "name": "Bob"})
    a.get_received(); b.get_received()

    a.emit("start_game_request", {"code": code})
    assert events(a, "trigger_start_game")
    assert events(b, "trigger_start_game")


def test_a_non_host_cannot_start_the_game(client, sock):
    # Any client could previously start the game just by emitting.
    code = room_with(client, "Alice", "Bob")
    a, b = sock(), sock()
    a.emit("join_lobby", {"code": code, "name": "Alice"})
    b.emit("join_lobby", {"code": code, "name": "Bob"})
    a.get_received(); b.get_received()

    b.emit("start_game_request", {"code": code})
    assert not events(a, "trigger_start_game")
    assert not events(b, "trigger_start_game")


def test_an_unconnected_socket_cannot_start_a_game(client, sock):
    code = room_with(client, "Alice")
    stranger = sock()
    stranger.emit("start_game_request", {"code": code})
    assert not events(stranger, "trigger_start_game")


# ---------------------------------------------------------------------------
# The game world
# ---------------------------------------------------------------------------

def test_join_game_tells_you_where_to_stand(client, sock):
    import maps

    code = room_with(client, "Alice")
    a = sock()
    a.emit("join_game", {"code": code, "name": "Alice"})

    first = maps.load(config.DEFAULT_MAP)["spawn_points"][0]
    joined = payloads(a, "game_joined")[0]
    assert joined["map"] == config.DEFAULT_MAP
    assert joined["you"]["name"] == "Alice"
    assert (joined["you"]["x"], joined["you"]["y"]) == (first["x"], first["y"])
    assert joined["players"] == []


def test_join_game_lists_players_already_in_the_world(client, sock):
    code = room_with(client, "Alice", "Bob")
    a, b = sock(), sock()
    a.emit("join_game", {"code": code, "name": "Alice"})
    a.get_received()

    b.emit("join_game", {"code": code, "name": "Bob"})
    joined = payloads(b, "game_joined")[0]
    assert [p["name"] for p in joined["players"]] == ["Alice"]

    # And Alice hears about Bob.
    assert payloads(a, "player_revealed")[0]["name"] == "Bob"


def test_you_are_not_announced_to_yourself(client, sock):
    code = room_with(client, "Alice")
    a = sock()
    a.emit("join_game", {"code": code, "name": "Alice"})
    assert not events(a, "player_revealed")


def test_players_carry_their_lobby_emoji_into_the_game(client, sock):
    code = room_with(client, "Alice")
    client.post("/change_emoji",
                json={"code": code, "name": "Alice", "emoji": config.EMOJI_POOL[-1]})

    a = sock()
    a.emit("join_game", {"code": code, "name": "Alice"})
    assert payloads(a, "game_joined")[0]["you"]["emoji"] == config.EMOJI_POOL[-1]


def test_movement_is_relayed_to_others_but_not_echoed(client, sock):
    code = room_with(client, "Alice", "Bob")
    a, b = sock(), sock()
    a.emit("join_game", {"code": code, "name": "Alice"})
    b.emit("join_game", {"code": code, "name": "Bob"})
    a.get_received(); b.get_received()

    b.emit("player_move", {"x": 640, "y": 480})
    moved = payloads(a, "player_moved")[0]
    assert (moved["x"], moved["y"]) == (640, 480)
    assert not events(b, "player_moved")


def test_junk_movement_is_ignored(client, sock):
    code = room_with(client, "Alice", "Bob")
    a, b = sock(), sock()
    a.emit("join_game", {"code": code, "name": "Alice"})
    b.emit("join_game", {"code": code, "name": "Bob"})
    a.get_received(); b.get_received()

    for bad in [{"x": "far", "y": 0}, {"x": None, "y": None}, {}, "nonsense"]:
        b.emit("player_move", bad)

    assert not events(a, "player_moved")
    assert b.is_connected()


def test_join_game_for_a_closed_room_is_rejected(client, sock):
    a = sock()
    a.emit("join_game", {"code": "0000", "name": "Alice"})
    assert events(a, "join_rejected")


# ---------------------------------------------------------------------------
# The lobby-to-game handover, which is what used to lose players
# ---------------------------------------------------------------------------

def test_leaving_the_lobby_for_the_game_keeps_you_in_the_room(client, sock):
    code = room_with(client, "Alice", "Bob")

    a_lobby, b_lobby = sock(), sock()
    a_lobby.emit("join_lobby", {"code": code, "name": "Alice"})
    b_lobby.emit("join_lobby", {"code": code, "name": "Bob"})

    # Everyone navigates to the game page: every lobby socket closes.
    a_lobby.disconnect()
    b_lobby.disconnect()

    # The room and both players must survive that.
    view = rooms.public_view(code)
    assert view is not None
    assert [p["name"] for p in view["players"]] == ["Alice", "Bob"]

    # And the game sockets pick them up again, host intact.
    a_game = sock()
    a_game.emit("join_game", {"code": code, "name": "Alice"})
    assert payloads(a_game, "game_joined")[0]["you"]["name"] == "Alice"
    assert rooms.is_host(code, "Alice")


def test_a_disconnect_stops_you_being_drawn_but_keeps_your_seat(client, sock):
    code = room_with(client, "Alice", "Bob")
    a, b = sock(), sock()
    a.emit("join_game", {"code": code, "name": "Alice"})
    b.emit("join_game", {"code": code, "name": "Bob"})
    a.get_received(); b.get_received()

    b.disconnect()

    received = a.get_received()
    assert payloads(received, "player_left")

    room = payloads(received, "room_updated")[-1]
    bob = [p for p in room["players"] if p["name"] == "Bob"][0]
    assert bob["connected"] is False


def test_reconnecting_resumes_where_you_were_standing(client, sock):
    code = room_with(client, "Alice")
    a = sock()
    a.emit("join_game", {"code": code, "name": "Alice"})
    a.get_received()
    a.emit("player_move", {"x": 1500, "y": 700})
    a.disconnect()

    again = sock()
    again.emit("join_game", {"code": code, "name": "Alice"})
    you = payloads(again, "game_joined")[0]["you"]
    assert (you["x"], you["y"]) == (1500, 700)


# ---------------------------------------------------------------------------
# Rounds over the wire
# ---------------------------------------------------------------------------

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


def in_world(client, sock, *names):
    """A room with everybody connected and on the game page."""
    code = room_with(client, *names)
    clients = {}
    for name in names:
        c = sock()
        c.emit("join_game", {"code": code, "name": name})
        c.get_received()
        clients[name] = c
    return code, clients


def test_the_host_starting_a_round_sends_everyone_to_the_game(client, sock):
    code = room_with(client, "Alice", "Bob")
    a, b = sock(), sock()
    a.emit("join_lobby", {"code": code, "name": "Alice"})
    b.emit("join_lobby", {"code": code, "name": "Bob"})
    a.get_received(); b.get_received()

    a.emit("start_game_request", {"code": code})

    assert events(b, "trigger_start_game")
    assert game.state(code)["phase"] == "gathering"


def test_a_round_with_nobody_to_seek_is_turned_down_with_a_reason(client, sock):
    code = room_with(client, "Alice")
    a = sock()
    a.emit("join_lobby", {"code": code, "name": "Alice"})
    a.get_received()

    a.emit("start_game_request", {"code": code})

    assert payloads(a, "start_rejected")[0]["message"]
    assert not events(a, "trigger_start_game")
    assert game.state(code)["phase"] == "lobby"


def test_starting_a_round_puts_players_already_in_the_world_back_on_the_base(client, sock):
    code, clients = in_world(client, sock, "Alice", "Bob")
    clients["Alice"].emit("player_move", {"x": 300, "y": 300})
    clients["Alice"].get_received()

    clients["Alice"].emit("start_game_request", {"code": code})

    corrected = payloads(clients["Alice"], "position_correction")[-1]
    assert (corrected["x"], corrected["y"]) != (300, 300)


def test_the_round_state_reaches_the_game_page(client, sock):
    code, clients = in_world(client, sock, "Alice", "Bob")
    clients["Alice"].emit("start_game_request", {"code": code})

    state = payloads(clients["Bob"], "game_state")[-1]
    assert state["phase"] in ("gathering", "counting")
    assert state["tagger"]


def test_joining_the_game_is_told_the_round_state(client, sock):
    code = room_with(client, "Alice")
    a = sock()
    a.emit("join_game", {"code": code, "name": "Alice"})

    joined = payloads(a, "game_joined")[0]
    assert joined["game"]["phase"] == "lobby"
    assert joined["map"] == config.DEFAULT_MAP


def test_a_hider_who_will_not_hold_still_is_put_back(client, sock):
    """The client is meant to refuse this itself; the server does not
    take its word for it."""
    code, clients = in_world(client, sock, "Alice", "Bob")
    clients["Alice"].emit("start_game_request", {"code": code})
    for c in clients.values():
        c.get_received()

    # Still gathering, so nobody may move at all.
    seeker = rooms.get(code)["players"]["alice"]
    was = (seeker["x"], seeker["y"])
    clients["Alice"].emit("player_move", {"x": 300, "y": 300})

    assert payloads(clients["Alice"], "position_correction")[-1] == {
        "x": was[0], "y": was[1],
    }
    assert (seeker["x"], seeker["y"]) == was


def test_a_position_the_server_already_agrees_with_draws_no_correction(client, sock):
    code, clients = in_world(client, sock, "Alice", "Bob")
    clients["Alice"].emit("start_game_request", {"code": code})
    for c in clients.values():
        c.get_received()

    alice = rooms.get(code)["players"]["alice"]
    # A keepalive from a player who has not moved is not a disagreement.
    clients["Alice"].emit("player_move", {"x": alice["x"], "y": alice["y"]})
    assert not events(clients["Alice"], "position_correction")


# ---------------------------------------------------------------------------
# Positions the server refuses to hand over
# ---------------------------------------------------------------------------

def start_hunting(code, monkeypatch, now=1000.0):
    """Drive a started round through the count without waiting for it."""
    held = {"now": now}
    monkeypatch.setattr(game, "_now", lambda: held["now"])

    game.start(code)
    game.resolve(code, force=True)
    held["now"] += config.COUNTDOWN_SECONDS + 1
    game.resolve(code, force=True)
    assert game.state(code)["phase"] == "hunting"

    # Everyone started on the base, so everyone was relocated and pinned.
    held["now"] += config.RELOCATE_PIN_SECONDS + 0.1
    return held


def test_a_faraway_player_is_never_sent_to_you(client, sock, monkeypatch):
    code, clients = in_world(client, sock, "Alice", "Bob")
    start_hunting(code, monkeypatch)

    players = rooms.get(code)["players"]
    players["alice"]["x"], players["alice"]["y"] = 200, 200
    for c in clients.values():
        c.get_received()

    # Bob reports a position on the far side of the house.
    clients["Bob"].emit("player_move", {"x": 2200, "y": 1400})

    # One drain, two questions of it: get_received empties the queue.
    received = clients["Alice"].get_received()
    assert not events(received, "player_moved")
    assert payloads(received, "player_hidden")[-1]["id"]


def test_coming_into_view_introduces_you_properly(client, sock, monkeypatch):
    """A client cannot draw somebody it was never told the name of."""
    code, clients = in_world(client, sock, "Alice", "Bob")
    start_hunting(code, monkeypatch)

    players = rooms.get(code)["players"]
    players["alice"]["x"], players["alice"]["y"] = 200, 200
    clients["Bob"].emit("player_move", {"x": 2200, "y": 1400})
    for c in clients.values():
        c.get_received()

    clients["Bob"].emit("player_move", {"x": 260, "y": 200})

    revealed = payloads(clients["Alice"], "player_revealed")[-1]
    assert revealed["name"] == "Bob"
    assert (revealed["x"], revealed["y"]) == (260, 200)


def test_the_seeker_is_sent_nobody_while_they_count(client, sock, monkeypatch):
    code, clients = in_world(client, sock, "Alice", "Bob")

    held = {"now": 1000.0}
    monkeypatch.setattr(game, "_now", lambda: held["now"])
    game.start(code)
    game.resolve(code, force=True)
    assert game.state(code)["phase"] == "counting"

    seeker_key = game.state(code)["tagger"]
    seeker_name = rooms.get(code)["players"][seeker_key]["name"]
    hider_name = next(n for n in clients if n != seeker_name)

    for c in clients.values():
        c.get_received()

    # The hider runs off; the seeker must not be told where.
    clients[hider_name].emit("player_move", {"x": 1180, "y": 700})

    received = clients[seeker_name].get_received()
    assert not events(received, "player_moved")
    assert not events(received, "player_revealed")


def test_a_hider_in_the_furniture_is_withheld_until_searched(client, sock, monkeypatch):
    code, clients = in_world(client, sock, "Alice", "Bob")
    held = start_hunting(code, monkeypatch)

    seeker_key = game.state(code)["tagger"]
    players = rooms.get(code)["players"]
    seeker_name = players[seeker_key]["name"]
    hider_name = next(n for n in clients if n != seeker_name)

    spot = hiding_spot("under the bed", corner=True)

    # The seeker stands in the same room, but not at the bed.
    players[seeker_key]["x"] = spot[0] + config.VISION_RADIUS - 60
    players[seeker_key]["y"] = spot[1]
    for c in clients.values():
        c.get_received()

    clients[hider_name].emit("player_move", {"x": spot[0], "y": spot[1]})
    received = clients[seeker_name].get_received()
    assert not events(received, "player_moved")
    assert not events(received, "player_revealed")

    # Now they walk up and search it.
    held["now"] += 1
    for c in clients.values():
        c.get_received()
    clients[seeker_name].emit(
        "player_move",
        {"x": spot[0] + config.SEARCH_DISTANCE - 20, "y": spot[1]},
    )

    assert payloads(clients[seeker_name], "player_revealed")[-1]["name"] == hider_name


def test_a_tag_lands_on_the_move_that_makes_contact(client, sock, monkeypatch):
    code, clients = in_world(client, sock, "Alice", "Bob")
    held = start_hunting(code, monkeypatch)

    seeker_key = game.state(code)["tagger"]
    players = rooms.get(code)["players"]
    seeker_name = players[seeker_key]["name"]
    hider_key = next(k for k in players if k != seeker_key)

    players[hider_key]["x"], players[hider_key]["y"] = 300, 300
    for c in clients.values():
        c.get_received()

    # Past the rate limit on move-driven checks, as any real frame would be.
    held["now"] += config.RESOLVE_INTERVAL_SECONDS * 2
    clients[seeker_name].emit("player_move", {"x": 320, "y": 300})

    assert players[hider_key]["state"] == "frozen"
    state = payloads(clients[seeker_name], "game_state")[-1]
    assert state["tally"]["frozen"] == 1


def test_backing_out_to_the_lobby_ends_a_finished_round(client, sock):
    code, clients = in_world(client, sock, "Alice", "Bob")
    clients["Alice"].emit("start_game_request", {"code": code})
    assert game.state(code)["phase"] == "gathering"

    # Both game sockets close as they navigate back, then rejoin the lobby.
    for c in clients.values():
        c.disconnect()

    a = sock()
    a.emit("join_lobby", {"code": code, "name": "Alice"})
    assert game.state(code)["phase"] == "lobby"
