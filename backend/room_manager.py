import random
import string

rooms = {}

def generate_room_code():
    return ''.join(random.choices("1234567890", k=6))

def create_room(display_name):
    code = generate_room_code()

    while code in rooms:
        code = generate_room_code()

    rooms[code] = {
        "players": [display_name]
    }

    return code

def join_room(code, display_name):
    if code not in rooms:
        return False

    rooms[code]["players"].append(display_name)
    return True

def get_room(code):
    return rooms.get(code)