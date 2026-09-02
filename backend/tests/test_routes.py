# -*- coding: utf-8 -*-
"""HTTP endpoints."""

import config
import rooms


def create(client, name="Alice"):
    return client.post("/create_room", json={"name": name}).get_json()["room_code"]


def test_pages_render(client):
    for path in ["/", "/room_page", "/game_page"]:
        assert client.get(path).status_code == 200


def test_create_room(client):
    body = client.post("/create_room", json={"name": "Alice"}).get_json()
    assert body["success"] and body["room_code"].isdigit()


def test_create_room_rejects_a_blank_name(client):
    response = client.post("/create_room", json={"name": "  "})
    assert response.status_code == 400
    assert not response.get_json()["success"]


def test_create_room_with_no_body(client):
    # Used to raise before the body was parsed defensively.
    assert client.post("/create_room").status_code == 400


def test_join_room(client):
    code = create(client)
    body = client.post("/join_room", json={"code": code, "name": "Bob"}).get_json()
    assert body["success"]
    assert [p["name"] for p in body["room"]["players"]] == ["Alice", "Bob"]


def test_join_room_reports_why_it_failed(client):
    code = create(client)
    body = client.post("/join_room", json={"code": code, "name": "alice"}).get_json()
    assert not body["success"] and "taken" in body["message"]


def test_join_unknown_room(client):
    body = client.post("/join_room", json={"code": "0000", "name": "Bob"}).get_json()
    assert not body["success"] and body["message"] == "Room not found"


def test_room_info(client):
    code = create(client)
    body = client.get(f"/room/{code}").get_json()
    assert body["players"][0] == {
        "name": "Alice",
        "emoji": config.EMOJI_POOL[0],
        "isHost": True,
        "connected": False,
    }


def test_room_info_404(client):
    assert client.get("/room/0000").status_code == 404


def test_room_info_does_not_leak_socket_ids_or_positions(client):
    code = create(client)
    rooms.enter_game("secret-sid", code, "Alice", "house1")

    player = client.get(f"/room/{code}").get_json()["players"][0]
    assert set(player) == {"name", "emoji", "isHost", "connected"}


def test_emoji_is_returned_as_a_character_not_an_escape(client):
    code = create(client)
    raw = client.get(f"/room/{code}").get_data(as_text=True)
    assert config.EMOJI_POOL[0] in raw


def test_change_emoji(client):
    code = create(client)
    free = config.EMOJI_POOL[-1]
    assert client.post("/change_emoji",
                       json={"code": code, "name": "Alice", "emoji": free}).get_json()["success"]
    assert client.get(f"/room/{code}").get_json()["players"][0]["emoji"] == free


def test_change_emoji_to_one_already_taken(client):
    code = create(client)
    client.post("/join_room", json={"code": code, "name": "Bob"})
    bobs = client.get(f"/room/{code}").get_json()["players"][1]["emoji"]

    body = client.post("/change_emoji",
                       json={"code": code, "name": "Alice", "emoji": bobs}).get_json()
    assert not body["success"] and body["message"] == "Emoji already taken!"


def test_change_emoji_rejects_something_not_in_the_pool(client):
    code = create(client)
    body = client.post("/change_emoji",
                       json={"code": code, "name": "Alice", "emoji": "\U0001F480"}).get_json()
    assert not body["success"]


def test_send_chat(client):
    code = create(client)
    assert client.post("/send_chat",
                       json={"code": code, "name": "Alice", "message": "hi"}).get_json()["success"]
    assert client.get(f"/room/{code}").get_json()["chat"] == [{"name": "Alice", "message": "hi"}]


def test_send_chat_to_unknown_room(client):
    response = client.post("/send_chat", json={"code": "0000", "name": "A", "message": "hi"})
    assert response.status_code == 404


def test_send_chat_from_someone_not_in_the_room(client):
    code = create(client)
    response = client.post("/send_chat",
                           json={"code": code, "name": "Mallory", "message": "hi"})
    assert response.status_code == 400
    assert not response.get_json()["success"]


def test_send_empty_chat(client):
    code = create(client)
    assert client.post("/send_chat",
                       json={"code": code, "name": "Alice", "message": "   "}).status_code == 400
