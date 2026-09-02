# -*- coding: utf-8 -*-
"""Room state: identity, validation, emoji, chat, and expiry."""

import time

import pytest

import config
import rooms


def make_room(host="Alice"):
    return rooms.create(host)


# ---------------------------------------------------------------------------
# Creating and joining
# ---------------------------------------------------------------------------

def test_create_returns_a_four_digit_code():
    code = make_room()
    assert len(code) == config.ROOM_CODE_LENGTH and code.isdigit()


def test_creator_is_host():
    code = make_room("Alice")
    assert rooms.is_host(code, "Alice")


def test_joining_player_is_not_host():
    code = make_room("Alice")
    assert rooms.add_player(code, "Bob") == (True, None)
    assert not rooms.is_host(code, "Bob")


def test_names_are_case_insensitive_identities():
    code = make_room("Alice")
    ok, message = rooms.add_player(code, "ALICE")
    assert not ok and "taken" in message


def test_surrounding_whitespace_does_not_make_a_new_player():
    code = make_room("Alice")
    ok, _ = rooms.add_player(code, "  alice  ")
    assert not ok


def test_join_unknown_room():
    ok, message = rooms.add_player("0000", "Bob")
    assert not ok and message == "Room not found"


@pytest.mark.parametrize("name", ["", "   ", None, 42, "x" * 17])
def test_unusable_names_are_rejected(name):
    assert rooms.clean_name(name) is None


def test_name_whitespace_is_collapsed():
    assert rooms.clean_name("  Big   Bird ") == "Big Bird"


def test_create_rejects_an_unusable_name():
    assert rooms.create("   ") is None


@pytest.mark.parametrize("code", ["", "abc", "12345", "123", None, "12a4"])
def test_malformed_room_codes_are_rejected(code):
    assert rooms.clean_code(code) is None


def test_none_code_does_not_become_the_string_none():
    # str(None) == "None" used to sneak through as a room code.
    assert rooms.get(None) is None


# ---------------------------------------------------------------------------
# Emoji
# ---------------------------------------------------------------------------

def test_players_get_distinct_emoji_on_join():
    code = make_room("Alice")
    rooms.add_player(code, "Bob")
    rooms.add_player(code, "Carol")

    emoji = [p["emoji"] for p in rooms.public_view(code)["players"]]
    assert len(set(emoji)) == 3


def test_can_pick_a_free_emoji():
    code = make_room("Alice")
    free = config.EMOJI_POOL[-1]
    assert rooms.set_emoji(code, "Alice", free) == (True, None)
    assert rooms.find_player(code, "Alice")["emoji"] == free


def test_cannot_take_someone_elses_emoji():
    code = make_room("Alice")
    rooms.add_player(code, "Bob")
    bobs = rooms.find_player(code, "Bob")["emoji"]

    ok, message = rooms.set_emoji(code, "Alice", bobs)
    assert not ok and message == "Emoji already taken!"


def test_reselecting_your_own_emoji_is_allowed():
    # Everyone used to start on the same emoji, which made the one you
    # already had look "taken" to you.
    code = make_room("Alice")
    mine = rooms.find_player(code, "Alice")["emoji"]
    assert rooms.set_emoji(code, "Alice", mine) == (True, None)


def test_emoji_must_come_from_the_pool():
    code = make_room("Alice")
    ok, message = rooms.set_emoji(code, "Alice", "<script>")
    assert not ok and "available" in message


def test_emoji_for_a_player_not_in_the_room():
    code = make_room("Alice")
    ok, _ = rooms.set_emoji(code, "Mallory", config.EMOJI_POOL[-1])
    assert not ok


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

def test_chat_message_is_stored_under_the_players_display_name():
    code = make_room("Alice")
    assert rooms.add_chat_message(code, "alice", "hello") == (True, None)
    assert rooms.public_view(code)["chat"] == [{"name": "Alice", "message": "hello"}]


def test_chat_is_capped():
    code = make_room("Alice")
    for i in range(config.MAX_CHAT_MESSAGES + 20):
        rooms.add_chat_message(code, "Alice", f"m{i}")

    chat = rooms.public_view(code)["chat"]
    assert len(chat) == config.MAX_CHAT_MESSAGES
    assert chat[-1]["message"] == f"m{config.MAX_CHAT_MESSAGES + 19}"


def test_long_chat_messages_are_truncated():
    code = make_room("Alice")
    rooms.add_chat_message(code, "Alice", "x" * 500)
    assert len(rooms.public_view(code)["chat"][0]["message"]) == config.MAX_CHAT_LENGTH


def test_empty_chat_message_is_rejected():
    code = make_room("Alice")
    ok, _ = rooms.add_chat_message(code, "Alice", "   ")
    assert not ok


def test_outsiders_cannot_post_to_a_room():
    code = make_room("Alice")
    ok, message = rooms.add_chat_message(code, "Mallory", "hi")
    assert not ok and "not in this room" in message


# ---------------------------------------------------------------------------
# Connections and expiry
# ---------------------------------------------------------------------------

def test_attach_binds_a_socket_to_an_existing_player():
    code = make_room("Alice")
    player = rooms.attach("sid-1", code, "Alice")
    assert player["sid"] == "sid-1"
    assert rooms.connected_player("sid-1")["name"] == "Alice"


def test_attach_refuses_a_player_who_never_joined():
    code = make_room("Alice")
    assert rooms.attach("sid-1", code, "Mallory") is None


def test_disconnect_keeps_the_player_in_the_room():
    # This is the lobby-to-game navigation case: the socket drops, but the
    # player must not vanish from the room.
    code = make_room("Alice")
    rooms.attach("sid-1", code, "Alice")
    rooms.detach("sid-1")

    view = rooms.public_view(code)
    assert [p["name"] for p in view["players"]] == ["Alice"]
    assert view["players"][0]["connected"] is False


def test_reconnecting_within_the_grace_period_keeps_your_place():
    code = make_room("Alice")
    rooms.attach("sid-1", code, "Alice")
    rooms.detach("sid-1")
    rooms.attach("sid-2", code, "Alice")

    view = rooms.public_view(code)
    assert view["players"][0]["connected"] is True
    assert view["players"][0]["isHost"] is True


def test_player_expires_after_the_grace_period(monkeypatch):
    code = make_room("Alice")
    rooms.add_player(code, "Bob")
    rooms.attach("sid-a", code, "Alice")
    rooms.attach("sid-b", code, "Bob")
    rooms.detach("sid-b")

    later = time.monotonic() + config.DISCONNECT_GRACE_SECONDS + 1
    monkeypatch.setattr(time, "monotonic", lambda: later)

    # Alice is still connected, so only Bob goes.
    assert [p["name"] for p in rooms.public_view(code)["players"]] == ["Alice"]


def test_a_room_nobody_ever_joins_is_cleaned_up(monkeypatch):
    code = make_room("Alice")
    later = time.monotonic() + config.DISCONNECT_GRACE_SECONDS + 1
    monkeypatch.setattr(time, "monotonic", lambda: later)

    assert rooms.public_view(code) is None


def test_creating_a_room_clears_out_abandoned_ones(monkeypatch):
    stale = make_room("Ghost")

    later = time.monotonic() + config.DISCONNECT_GRACE_SECONDS + 1
    monkeypatch.setattr(time, "monotonic", lambda: later)

    make_room("Alice")
    assert rooms.get(stale) is None


def test_room_disappears_once_everyone_has_expired(monkeypatch):
    code = make_room("Alice")
    later = time.monotonic() + config.DISCONNECT_GRACE_SECONDS + 1
    monkeypatch.setattr(time, "monotonic", lambda: later)

    assert rooms.public_view(code) is None


def test_host_is_reassigned_when_the_host_expires(monkeypatch):
    # Previously the room was left with no host and no way to start.
    code = make_room("Alice")
    rooms.add_player(code, "Bob")
    rooms.add_player(code, "Carol")
    rooms.attach("sid-b", code, "Bob")
    rooms.attach("sid-c", code, "Carol")

    later = time.monotonic() + config.DISCONNECT_GRACE_SECONDS + 1
    monkeypatch.setattr(time, "monotonic", lambda: later)

    view = rooms.public_view(code)
    assert [p["name"] for p in view["players"]] == ["Bob", "Carol"]
    assert view["players"][0]["isHost"] and not view["players"][1]["isHost"]


def test_a_second_socket_for_the_same_player_takes_over():
    code = make_room("Alice")
    rooms.attach("sid-1", code, "Alice")
    rooms.attach("sid-2", code, "Alice")

    assert rooms.connected_player("sid-1") is None
    assert rooms.connected_player("sid-2")["name"] == "Alice"

    # The stale socket closing must not knock the live one offline.
    rooms.detach("sid-1")
    assert rooms.public_view(code)["players"][0]["connected"] is True


# ---------------------------------------------------------------------------
# The game world
# ---------------------------------------------------------------------------

def test_entering_the_game_uses_a_map_spawn_point():
    code = make_room("Alice")
    player = rooms.enter_game("sid-1", code, "Alice", "house1")
    assert (player["x"], player["y"]) == (120, 120)


def test_players_spawn_on_different_points():
    # They all used to appear stacked on (100, 100).
    code = make_room("Alice")
    rooms.add_player(code, "Bob")

    a = rooms.enter_game("sid-a", code, "Alice", "house1")
    b = rooms.enter_game("sid-b", code, "Bob", "house1")
    assert (a["x"], a["y"]) != (b["x"], b["y"])


def test_rejoining_the_game_does_not_move_you_back_to_spawn():
    code = make_room("Alice")
    rooms.enter_game("sid-1", code, "Alice", "house1")
    rooms.move("sid-1", 900, 800)
    rooms.detach("sid-1")

    player = rooms.enter_game("sid-2", code, "Alice", "house1")
    assert (player["x"], player["y"]) == (900, 800)


def test_move_updates_position():
    code = make_room("Alice")
    rooms.enter_game("sid-1", code, "Alice", "house1")

    got_code, player = rooms.move("sid-1", 12.5, -3)
    assert got_code == code and (player["x"], player["y"]) == (12.5, -3.0)


@pytest.mark.parametrize("bad", ["100", None, True, float("nan"), float("inf"), {}])
def test_move_rejects_junk_coordinates(bad):
    code = make_room("Alice")
    rooms.enter_game("sid-1", code, "Alice", "house1")
    assert rooms.move("sid-1", bad, 0) == (None, None)


def test_move_from_an_unknown_socket_is_ignored():
    assert rooms.move("nobody", 1, 2) == (None, None)


def test_players_in_game_excludes_the_lobby_and_the_asker():
    code = make_room("Alice")
    rooms.add_player(code, "Bob")
    rooms.add_player(code, "Carol")

    rooms.enter_game("sid-a", code, "Alice", "house1")
    rooms.enter_game("sid-b", code, "Bob", "house1")
    rooms.attach("sid-c", code, "Carol")  # lobby only

    names = [p["name"] for p in rooms.players_in_game(code, exclude_sid="sid-a")]
    assert names == ["Bob"]
