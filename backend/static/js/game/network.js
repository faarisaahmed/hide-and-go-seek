/*
 * Multiplayer: tell the server where we are, and keep a picture of where
 * everyone else is.
 *
 * Remote positions are applied directly rather than eased towards, so
 * what you see is exactly the last position the server sent. With a tick
 * every ~16ms that reads as smooth, and it keeps everyone's view of a
 * player's position identical.
 */

import { NETWORK_TICK_MS } from "./config.js";

/* Remote players, keyed by their socket id. */
const remotePlayers = {};

export function getRemotePlayers() {
    return remotePlayers;
}

/*
 * Connect, announce ourselves, and start reporting our position.
 * `localPlayer` is read on every tick, so movement needs no extra plumbing.
 */
export function connect({ code, name, localPlayer }) {
    const socket = io();

    socket.on("player_joined_game", (data) => {
        remotePlayers[data.id] = { x: data.x, y: data.y, name: data.name };
    });

    socket.on("player_moved", (data) => {
        const player = remotePlayers[data.id];
        // Ignore movement from someone we have not been introduced to yet.
        if (!player) return;

        player.x = data.x;
        player.y = data.y;
    });

    socket.on("player_left", (data) => {
        delete remotePlayers[data.id];
    });

    socket.emit("join_game", { code, name });

    setInterval(() => {
        socket.emit("player_move", { x: localPlayer.x, y: localPlayer.y });
    }, NETWORK_TICK_MS);

    return socket;
}
