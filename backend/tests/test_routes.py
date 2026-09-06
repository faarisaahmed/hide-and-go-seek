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
        "volunteer": False,
        "bot": False,
    }


def test_room_info_404(client):
    assert client.get("/room/0000").status_code == 404


def test_room_info_does_not_leak_socket_ids_or_positions(client):
    code = create(client)
    rooms.enter_game("secret-sid", code, "Alice", "house1")

    player = client.get(f"/room/{code}").get_json()["players"][0]
    assert set(player) == {"name", "emoji", "isHost", "connected",
                           "volunteer", "bot"}


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


# ---------------------------------------------------------------------------
# Volunteering to be the seeker
# ---------------------------------------------------------------------------

def test_volunteering_is_reflected_in_the_room(client):
    code = create(client)
    assert client.post("/volunteer",
                       json={"code": code, "name": "Alice",
                             "volunteer": True}).get_json()["success"]

    assert client.get(f"/room/{code}").get_json()["players"][0]["volunteer"]


def test_a_hand_can_come_back_down(client):
    code = create(client)
    client.post("/volunteer", json={"code": code, "name": "Alice",
                                    "volunteer": True})
    client.post("/volunteer", json={"code": code, "name": "Alice",
                                    "volunteer": False})

    assert not client.get(f"/room/{code}").get_json()["players"][0]["volunteer"]


def test_you_cannot_volunteer_into_a_room_you_are_not_in(client):
    code = create(client)
    response = client.post("/volunteer", json={"code": code, "name": "Mallory",
                                               "volunteer": True})
    assert response.status_code == 400


def test_volunteering_in_a_room_that_is_gone(client):
    response = client.post("/volunteer", json={"code": "0000", "name": "Alice",
                                               "volunteer": True})
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# The host removing somebody
# ---------------------------------------------------------------------------

def test_the_host_can_remove_a_player(client):
    code = create(client)
    client.post("/join_room", json={"code": code, "name": "Bob"})

    response = client.post("/kick", json={"code": code, "name": "Alice",
                                          "target": "Bob"})
    assert response.get_json()["success"]

    names = [p["name"] for p in client.get(f"/room/{code}").get_json()["players"]]
    assert names == ["Alice"]


def test_only_the_host_can_remove_anybody(client):
    """The × is only rendered on the host's screen, which is not the same
    as it only working there."""
    code = create(client)
    client.post("/join_room", json={"code": code, "name": "Bob"})
    client.post("/join_room", json={"code": code, "name": "Carol"})

    response = client.post("/kick", json={"code": code, "name": "Bob",
                                          "target": "Carol"})
    assert response.status_code == 403

    names = [p["name"] for p in client.get(f"/room/{code}").get_json()["players"]]
    assert "Carol" in names


def test_the_host_cannot_remove_themselves(client):
    """Leaving is what the Leave button is for; doing it here would hand
    the room to somebody by accident."""
    code = create(client)
    client.post("/join_room", json={"code": code, "name": "Bob"})

    response = client.post("/kick", json={"code": code, "name": "Alice",
                                          "target": "Alice"})
    assert response.status_code == 400
    assert rooms.is_host(code, "Alice")


def test_removing_somebody_who_is_not_there(client):
    code = create(client)
    response = client.post("/kick", json={"code": code, "name": "Alice",
                                          "target": "Nobody"})
    assert response.status_code == 400


def test_removing_from_a_room_that_is_gone(client):
    response = client.post("/kick", json={"code": "0000", "name": "Alice",
                                          "target": "Bob"})
    assert response.status_code == 404
