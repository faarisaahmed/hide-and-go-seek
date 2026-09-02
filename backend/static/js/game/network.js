/*
 * Multiplayer: tell the server where we are, and keep a picture of where
 * everyone else is.
 *
 * The server decides which map to load, where each player spawns, and —
 * crucially — which of the other players we are told about at all. A
 * hider inside a wardrobe is not sent to the seeker, so there is nothing
 * for a modified client to draw. That is why positions arrive as three
 * separate events rather than one broadcast:
 *
 *   player_revealed  somebody came into sight; here is everything
 *   player_moved     somebody in sight moved; here is where
 *   player_hidden    somebody slipped out of sight; stop drawing them
 *
 * Each remote player carries both where they are being drawn (x, y) and
 * the last position the server sent (tx, ty). Drawing the raw server
 * position was fine over a LAN; over the internet the updates arrive
 * unevenly and it reads as a slideshow, so the drawn position is eased
 * towards the target every frame instead. See interpolateRemotes.
 */

import {
    NETWORK_TICK_MS,
    POSITION_KEEPALIVE_MS,
    REMOTE_SMOOTHING_SECONDS,
    REMOTE_SNAP_DISTANCE,
} from "./config.js";
import { applyState } from "./round.js";

/* Remote players we can currently see, keyed by their socket id. */
const remotePlayers = {};

export function getRemotePlayers() {
    return remotePlayers;
}

/*
 * Connect and announce ourselves.
 *
 * Resolves once the server has told us where to spawn, with the map name
 * to load. Rejects if the room is gone, so the caller can send the player
 * back to the home page.
 */
export function join({ code, name, localPlayer }) {
    const socket = io();

    return new Promise((resolve, reject) => {
        socket.on("game_joined", (data) => {
            localPlayer.x = data.you.x;
            localPlayer.y = data.you.y;
            localPlayer.emoji = data.you.emoji;

            for (const player of data.players) {
                remotePlayers[player.id] = { ...player, tx: player.x, ty: player.y };
            }

            applyState(data.game);
            startReporting(socket, localPlayer);
            resolve({ socket, map: data.map });
        });

        socket.on("join_rejected", (data) => {
            reject(new Error(data.message || "Could not join the game."));
        });

        socket.on("player_revealed", (data) => {
            // Someone stepping into view has no history to smooth from,
            // so they appear exactly where they are.
            remotePlayers[data.id] = { ...data, tx: data.x, ty: data.y };
        });

        socket.on("player_moved", (data) => {
            const player = remotePlayers[data.id];
            // Ignore movement from someone we cannot see; the server will
            // introduce them properly when we can.
            if (!player) return;

            player.tx = data.x;
            player.ty = data.y;
        });

        socket.on("player_hidden", (data) => {
            delete remotePlayers[data.id];
        });

        socket.on("player_left", (data) => {
            delete remotePlayers[data.id];
        });

        socket.on("game_state", applyState);

        // Sent when a new round puts us back on the base, and as a
        // correction if we tried to move while counting or frozen.
        socket.on("position_correction", (data) => {
            localPlayer.x = data.x;
            localPlayer.y = data.y;
        });

        socket.emit("join_game", { code, name });
    });
}

/*
 * Report our position, but only when it actually changed. A resend every
 * so often covers a dropped packet without flooding the server with
 * sixty identical messages a second while standing still.
 */
function startReporting(socket, localPlayer) {
    let lastX = null;
    let lastY = null;
    let lastSentAt = 0;

    setInterval(() => {
        const moved = localPlayer.x !== lastX || localPlayer.y !== lastY;
        const stale = Date.now() - lastSentAt > POSITION_KEEPALIVE_MS;
        if (!moved && !stale) return;

        socket.emit("player_move", { x: localPlayer.x, y: localPlayer.y });
        lastX = localPlayer.x;
        lastY = localPlayer.y;
        lastSentAt = Date.now();
    }, NETWORK_TICK_MS);
}


/*
 * Ease every remote player towards the last position the server sent.
 *
 * Exponential smoothing, so the rate does not depend on the frame rate:
 * whatever fraction of the gap is closed in a second is the same on a
 * 60Hz laptop and a 120Hz phone.
 */
export function interpolateRemotes(dt) {
    const caught = 1 - Math.exp(-dt / REMOTE_SMOOTHING_SECONDS);

    for (const player of Object.values(remotePlayers)) {
        const dx = player.tx - player.x;
        const dy = player.ty - player.y;

        if (Math.hypot(dx, dy) > REMOTE_SNAP_DISTANCE) {
            player.x = player.tx;
            player.y = player.ty;
            continue;
        }

        player.x += dx * caught;
        player.y += dy * caught;
    }
}
