# -*- coding: utf-8 -*-
"""Socket.IO protocol, including the lobby-to-game handover."""

import config
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
    assert payloads(a, "player_joined_game")[0]["name"] == "Bob"


def test_you_are_not_announced_to_yourself(client, sock):
    code = room_with(client, "Alice")
    a = sock()
    a.emit("join_game", {"code": code, "name": "Alice"})
    assert not events(a, "player_joined_game")


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
