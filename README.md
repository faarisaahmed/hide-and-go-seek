# Hide and Go Seek

**[Play it](https://hide-and-go-seek.onrender.com)** ·
[About](https://faarisaahmed.github.io/hide-and-go-seek/)

A browser-based multiplayer hide-and-seek game, played over a house. Flask
+ Socket.IO on the server, plain HTML/CSS/Canvas on the client — no build
step required.

The hosted copy is on a free plan and sleeps when nobody is playing, so a
first visit after a quiet spell takes about thirty seconds to wake up —
and waking up clears any rooms that were open, since rooms only ever live
in memory.

Nothing is loaded from the internet at runtime: the Socket.IO client is
vendored in `static/vendor/` and the design uses system fonts. That way the
game works on a Wi-Fi network with no upstream connection.

## The rules

One player is the **seeker**. Everybody starts on the **home base** in the
middle of the house.

1. The seeker shuts their eyes and counts to twenty. Their screen goes
   black and the server stops sending them anybody's position, so counting
   is a real cost rather than a formality.
2. Everybody else scatters and hides. Anyone still loitering within
   `NO_HIDE_RADIUS` of the base when the count ends is moved out to a
   proper hiding spot — camping the base is not hiding.
3. The seeker hunts. Touching a hider **freezes** them where they stand.
4. A hider who is still free can stand with a frozen team-mate for
   `RESCUE_HOLD_SECONDS` to **thaw** them. Someone who already made it
   home cannot, so a rescue always costs somebody their safety.
5. **Hiders win** by getting every one of themselves back onto the base.
   **The seeker wins** by freezing everyone, or by running out the clock.

Then the host can deal again, and the seeker rotates.

## The modes

Those are the rules of **Classic**. The host picks a mode in the lobby
before starting, and everyone else can see the choice — they need to know
what they are about to be dropped into even though they cannot change it.
The round takes a copy when it starts, so nobody can rewrite the rules of
a hunt already in progress.

**Infection.** Get tagged and you join the seekers rather than freezing.
The house fills up with them, so the round accelerates as it goes: every
catch is one fewer person to find and one more pair of eyes looking for
the rest. Being the last one still hiding is genuinely unpleasant.

**Juggernaut.** No hiding and no rescues. Furniture is just furniture,
a tag is final, and the clock is short. There is nothing between you and
the base except the seeker, which makes it the one to play when people
want a chase rather than a search.

**Blackout.** The lights are out. Everyone sees about a room's worth in
every direction, and the seeker trades that circle for a torch: narrower,
but reaching most of the way down a corridor and pointing only where they
last moved. That trade is the mode — a seeker who sees further than
anybody can still be walked around behind.

**Sardines.** Backwards. One player hides and the whole room goes
looking; find them and you squeeze in and hide too, so the wardrobe fills
up while the search gets lonelier. Last one still looking loses.

A mode is a dict in `modes.py` answering a fixed set of questions — how
many seekers, what a tag does, whether rescues exist, whether furniture
conceals, how far anyone sees, how long the hunt runs. `game.py` reads
those answers rather than reaching for `config.py` directly, so adding a
mode is a dict rather than another branch threaded through the round.

### The house

Twelve rooms around a corridor spine, with the base in the hall at the
centre: living room, kitchen, study, bedroom with an ensuite and a
walk-in closet, dining room, laundry with a cellar off it, games room,
kids' room, playroom. Rooms differ in size and shape on purpose — a
grid of identical boxes is a maze, not a house.

Floors are wood, tile, carpet or concrete and are drawn as such, walls
cast a shadow, doorways get a threshold, and the windows throw
moonlight across the floor. Some of that is atmosphere, but the floor
materials and the light do real work: they are how you tell which room
you have run into when you can only see a few metres.

### Hiding actually hides

The house is furnished, and some of that furniture is hollow — a wardrobe,
under a bed, a laundry basket, a play tent, the curtains. Standing in one
makes you invisible to the seeker until they walk within `SEARCH_DISTANCE`
and search it. Your own team can always see you, which is what makes
rescues possible.

Beyond the mode's sight radius nobody is drawn at all — and in Blackout,
outside the seeker's torch either. That filter lives on the **server**
(`game.can_see`), not the client: positions the seeker is not entitled to
are never sent, so there is nothing for a modified client to draw.
Everything else that decides the round — tags, thaws, reaching home, who
won — is decided server-side too.

The client is told the active mode's numbers along with the round, so the
darkness it paints and the torch it draws are the same shape as the
filter the server is applying. It keeps its own copy of the distances
only so it can grey out the joystick and draw a search radius without
waiting for a round trip.

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

## Playing with friends who are not on your Wi-Fi

```bash
./scripts/share.sh
```

Starts the game, opens a tunnel to it, and prints an `https://` address
anyone in the world can open. No account and nothing touching your
router; the address dies when you press Ctrl-C.

It tries a Cloudflare Quick Tunnel first and falls back to localhost.run
over plain `ssh`, and it fetches the home page over each candidate before
handing it to you — a tunnel can connect perfectly happily and still hand
back an address that never gets a DNS record, which is not something you
want to discover by way of five friends telling you the link is broken.

For an address that stays put, the repo also carries `render.yaml`, a
`Dockerfile` and a `Procfile`. See **[DEPLOY.md](DEPLOY.md)** — including
the two things that will silently ruin a deployment if you change the
start command (one worker, and a websocket-capable one).

Playing across the internet rather than a room does change the game
slightly: remote players are eased towards the last position the server
sent rather than snapped to it, which costs about 80ms of lag and buys
motion that does not stutter.

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests -q
```

Covers room state and expiry, the HTTP API, the socket protocol, and the
whole round: role assignment, each phase transition, tagging, thawing, both
win conditions, and — the one worth having — that a hidden player is never
sent to the seeker over the wire.

`test_modes.py` covers each mode's own rules, mostly in pairs: a hider in
the wardrobe is visible in Juggernaut and invisible in Classic from the
same spot, and somebody standing behind a Blackout seeker is unseen until
the seeker turns round. A single-sided assertion there would pass just as
happily if the two players were simply too far apart.

`test_maps.py` treats the house as something that has to be *playable*: it
flood-fills from the base with a player-sized box to prove every room and
every hiding spot can be walked to, which is what catches a sideboard
parked across a doorway. It also checks no hiding spot sits inside the
no-hide radius, since that is where the game relocates people to.

There are also checks that the browser code and the server have not
drifted: the emoji picker matching the server's pool, the shared distances
in `js/game/config.js` matching `config.py`, and every element the scripts
look up existing in the page they run on.

## How a game flows

1. **Home** (`/`) — enter a display name, then create a room or join one
   with its 4-digit code.
2. **Lobby** (`/room_page`) — see who's in the room, pick an emoji, chat,
   read the rules and the controls. The host picks the mode and gets a
   **Start game** button.
3. **Game** (`/game_page`) — WASD/arrows and Shift to sprint, or the
   on-screen joystick and B button on touch devices. The HUD tells you
   your role, what you should be doing about it, and how the round stands.
   When it ends, the host can start another from the results card.

Movement is in pixels per *second* and scaled by frame time, so a 120Hz
phone and a 60Hz laptop move at the same speed, and diagonals are
normalised so two keys are not faster than one.

**Sprinting costs stamina.** A full bar is about four seconds of running
and takes seven to come back, and emptying it locks sprint off until it
has recovered a good way — so you cannot tap the button for a permanent
boost. It is a feel mechanic and lives on the client: the server takes
each client's word for its own position, as it always has, so this
shapes a chase rather than being a rule anyone is held to.

Players are identified by name within a room. A socket dropping — which is
what happens when you move from the lobby to the game, or refresh — does
not remove you: the server holds your place for a short grace period
(`DISCONNECT_GRACE_SECONDS`) and you resume where you were standing. If
the host leaves for good, the longest-standing player takes over.

## Layout

```
backend/
  app.py            Flask + Socket.IO app factory and dev entrypoint
  config.py         Tunable constants (port, emoji pool, round rules)
  game.py           The round: roles, phases, tagging, thawing, winning
  modes.py          The game modes, as data: what each one changes
  maps.py           Reads map JSON: spawns, the base, hiding spots
  extensions.py     The shared SocketIO object
  rooms.py          In-memory room + player store
  routes.py         HTTP endpoints (pages and room JSON API)
  events.py         Socket.IO handlers, and the per-player position filter
  static/
    css/            style.css (tokens + shared components), game.css
    vendor/         Socket.IO client, served locally rather than from a CDN
    js/             session.js, api.js, home.js, lobby.js
    js/game/        config, input, map_loader, physics, network, round,
                    stamina, renderer, hud, and main.js which ties them
                    together
    maps/           Map definitions as JSON: rooms, walls, doorways,
                    windows, furniture, base zones, spawn points
  templates/        Jinja templates (base.html holds shared <head>)
  tests/            pytest suite
scripts/share.sh    Start the game behind a public tunnel
Procfile            }
render.yaml         } deploy targets — see DEPLOY.md
Dockerfile          }
```

Timers are advanced by a Socket.IO background task (`events._tick`), not by
player input, because the count has to keep running while the seeker is
standing perfectly still with their eyes shut.

Room state lives in memory only, so restarting the server clears all rooms.
