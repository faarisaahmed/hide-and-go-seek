# -*- coding: utf-8 -*-

import random

rooms = {}

EMOJI_POOL = [
    "😀","😃","😄","😁","😆",
    "😊","🙂","🥲","😢","😎",
    "🤠","🥳","😺","🐸"
]

def generate_room_code():
    return ''.join(random.choices("0123456789", k=6))

def get_available_emoji(room):
    if not room:
        return random.choice(EMOJI_POOL)

    used = [p.get("emoji") for p in room["players"] if "emoji" in p]

    for emoji in EMOJI_POOL:
        if emoji not in used:
            return emoji

    return random.choice(EMOJI_POOL)

def create_room(display_name):
    code = generate_room_code()

    while code in rooms:
        code = generate_room_code()

    emoji = random.choice(EMOJI_POOL)

    rooms[code] = {
        "players": [{
            "name": display_name,
            "emoji": emoji
        }],
        "chat": []
    }

    return code

def join_room(code, display_name):
    if not code or not display_name:
        return False

    if code not in rooms:
        return False

    room = rooms[code]

    # Prevent duplicate usernames
    for p in room["players"]:
        if p["name"] == display_name:
            return False

    emoji = get_available_emoji(room)

    room["players"].append({
        "name": display_name,
        "emoji": emoji
    })

    return True

def get_room(code):
    return rooms.get(code)

def add_chat_message(code, name, message):
    if code not in rooms:
        return False

    rooms[code]["chat"].append({
        "name": name,
        "message": message
    })

    # Limit chat size (important for memory)
    if len(rooms[code]["chat"]) > 50:
        rooms[code]["chat"].pop(0)

    return True