# Putting the game somewhere your friends can reach it

Two ways, depending on whether you want an address for tonight or an
address that stays.

## Tonight: a tunnel

```bash
./scripts/share.sh
```

Starts the server, opens a tunnel to it, and prints an `https://` address
anyone in the world can open. No account, no port forwarding, nothing
touching your router. The address is new every run and stops working when
you press Ctrl-C — which is usually what you want, since it is your
laptop on the other end of it.

Two providers are tried in turn:

1. **Cloudflare Quick Tunnel**, if `cloudflared` is installed
   (`brew install cloudflared`).
2. **localhost.run**, over plain `ssh`. Nothing to install.

It tries them *in turn* rather than picking one because printing an
address and that address working are different things. Cloudflare in
particular hands one over the moment it is assigned, while the DNS record
behind it is created separately — and when that does not appear, you get
a perfectly healthy tunnel on an address that resolves to nothing. So the
script fetches the home page over each candidate before handing it to
you, and moves to the next if nothing answers.

Force one with `./scripts/share.sh --via localhost.run`.

## For keeps: deploy it

The repo has config for the two usual shapes of host.

### Render

Point Render at this repo. It reads `render.yaml` and needs nothing
else. The free plan sleeps after inactivity, so the first person to open
it in a while waits ~30 seconds — and a sleep clears every room, because
rooms are only ever held in memory.

### A container: Fly, Railway, a VPS

```bash
docker build -t hide-and-go-seek .
docker run -p 5000:5000 hide-and-go-seek
```

`Procfile` covers anything that reads one.

## Two things that will bite you

**One worker, always.** Every config here pins `-w 1`. Rooms live in one
process's memory (`backend/rooms.py`), so a second worker is a second,
separate set of rooms: your friends type the right code and are told it
does not exist, about half the time. Nothing errors — it just quietly
does not work. `tests/test_deploy.py` pins this.

**WebSocket, not polling.** The gunicorn worker is
`GeventWebSocketWorker` for a reason. A plain worker cannot upgrade the
connection, everyone silently drops to HTTP long-polling, and a game
that felt fine on a LAN feels awful across the country. If you change
the start command, keep the worker class. Locally the equivalent is
`simple-websocket`, which is already in `requirements.txt`.

## Playing over the internet, honestly

- **Room codes are four digits.** Nine thousand of them. On a LAN that is
  plenty; on a public URL somebody could in principle walk the range and
  land in your lobby. The worst they can do is join a game of hide and
  seek, so this is a note rather than a warning — but if you leave a
  deployment up permanently, that is the thing to know about it.
- **A restart clears every room.** Nothing is stored. Mid-round restarts
  are not recoverable, so redeploy between games.
- **Distance costs you.** Remote players are drawn eased towards the last
  position the server sent (`REMOTE_SMOOTHING_SECONDS`), which trades
  about 80ms of lag for motion that is not a slideshow. Tags are decided
  on the server from the positions it has, so on a bad connection you can
  be tagged a moment after you thought you were clear.
