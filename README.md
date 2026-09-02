# Hide and Go Seek

A browser-based multiplayer hide-and-seek game. Flask + Socket.IO on the
server, plain HTML/CSS/Canvas on the client — no build step required.

## Running locally

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000. To play with other devices on the same
Wi-Fi, they can open `http://<your-computer-ip>:5000` instead — the client
talks to whatever host served the page, so no config change is needed.

If port 5000 is taken (macOS hands it to AirPlay Receiver when that is on),
run `PORT=5050 python app.py`.

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests -q
```

Covers room state and expiry, the HTTP API, the socket protocol, and a few
checks that the browser code and the server have not drifted apart (the
emoji picker matching the server's pool, every page asset resolving).

## How a game flows

1. **Home** (`/`) — enter a display name, then create a room or join one
   with its 4-digit code.
2. **Lobby** (`/room_page`) — see who's in the room, pick an emoji, chat.
   The host gets a **Start Game** button.
3. **Game** (`/game_page`) — everyone is moved into the canvas world and
   can run around with WASD/arrows (hold Shift to sprint) or the on-screen
   joystick and B button on touch devices. The server picks each player's
   spawn from the map's `spawn_points`, so nobody starts stacked up.

Players are identified by name within a room. A socket dropping — which is
what happens when you move from the lobby to the game, or refresh — does
not remove you: the server holds your place for a short grace period
(`DISCONNECT_GRACE_SECONDS`) and you resume where you were standing. If
the host leaves for good, the longest-standing player takes over.

## Layout

```
backend/
  app.py            Flask + Socket.IO app factory and dev entrypoint
  config.py         Tunable constants (port, emoji pool, limits, grace)
  maps.py           Reads map JSON so the server can assign spawns
  extensions.py     The shared SocketIO object
  rooms.py          In-memory room + player store
  routes.py         HTTP endpoints (pages and room JSON API)
  events.py         Socket.IO event handlers
  static/
    css/            style.css (home + lobby), game.css (game screen)
    js/             session.js, api.js, home.js, lobby.js
    js/game/        config, input, map_loader, physics, network,
                    renderer, and main.js which ties them together
    maps/           Map definitions as JSON
  templates/        Jinja templates (base.html holds shared <head>)
  tests/            pytest suite
```

Room state lives in memory only, so restarting the server clears all rooms.
