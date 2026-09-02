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

## How a game flows

1. **Home** (`/`) — enter a display name, then create a room or join one
   with its 4-digit code.
2. **Lobby** (`/room_page`) — see who's in the room, pick an emoji, chat.
   The host gets a **Start Game** button.
3. **Game** (`/game_page`) — everyone is moved into the canvas world and
   can run around with WASD/arrows (hold Shift to sprint) or the on-screen
   joystick and B button on touch devices.

## Layout

```
backend/
  app.py            Flask + Socket.IO app factory and dev entrypoint
  config.py         Tunable constants (port, spawn point, limits)
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
```

Room state lives in memory only, so restarting the server clears all rooms.
