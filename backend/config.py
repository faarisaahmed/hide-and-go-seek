# -*- coding: utf-8 -*-
"""Tunable constants for the server.

Kept in one place so gameplay numbers can be adjusted without hunting
through the request handlers.
"""

# Dev server
HOST = "0.0.0.0"
PORT = 5000
DEBUG = True

# Room codes are numeric so they are easy to read out loud and type on a
# phone. Four digits gives 9000 possible codes, which is plenty for a
# game played over one Wi-Fi network.
ROOM_CODE_MIN = 1000
ROOM_CODE_MAX = 9999

# Every player starts with this emoji and can change it in the lobby.
DEFAULT_EMOJI = "\U0001F600"  # 😀

# Where a player appears when they enter the game world.
SPAWN_X = 100
SPAWN_Y = 100

# Oldest chat messages are dropped past this many, so a long-running room
# cannot grow without bound.
MAX_CHAT_MESSAGES = 50
