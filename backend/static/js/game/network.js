/*
 * Multiplayer: tell the server where we are, and keep a picture of where
 * everyone else is.
 *
 * The server decides which map to load and where each player spawns, so
 * nobody starts stacked on the same tile and client and server cannot
 * disagree about the world.
 *
 * Remote positions are applied directly rather than eased towards, so
 * what you see is the last position the server sent. With updates arriving
 * as fast as players move, that reads as smooth.
 */

import { POSITION_KEEPALIVE_MS, NETWORK_TICK_MS } from "./config.js";

/* Remote players, keyed by their socket id. */
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
                remotePlayers[player.id] = player;
            }

            startReporting(socket, localPlayer);
            resolve({ socket, map: data.map });
        });

        socket.on("join_rejected", (data) => {
            reject(new Error(data.message || "Could not join the game."));
        });

        socket.on("player_joined_game", (data) => {
            remotePlayers[data.id] = data;
        });

        socket.on("player_moved", (data) => {
            const player = remotePlayers[data.id];
            // Ignore movement from someone we have not been introduced to.
            if (!player) return;

            player.x = data.x;
            player.y = data.y;
        });

        socket.on("player_left", (data) => {
            delete remotePlayers[data.id];
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
