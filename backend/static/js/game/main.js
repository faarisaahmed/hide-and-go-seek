/*
 * Game entrypoint (/game_page).
 *
 * Owns the local player and the frame loop, and hands the other modules
 * what they need: input reports intent, physics resolves it against the
 * map, network syncs it, renderer draws the result.
 */

import { requireSession } from "../session.js";
import { PLAYER_SIZE } from "./config.js";
import { initTouchControls, readMovement } from "./input.js";
import { loadMap } from "./map_loader.js";
import { getRemotePlayers, join } from "./network.js";
import { moveWithCollision } from "./physics.js";
import { createRenderer } from "./renderer.js";

async function start() {
    const session = requireSession();
    if (!session) return;

    // Filled in by the server, which decides where everyone spawns.
    const localPlayer = { x: 0, y: 0, size: PLAYER_SIZE, name: session.name, emoji: "" };

    let map;
    try {
        const joined = await join({ code: session.code, name: session.name, localPlayer });
        map = await loadMap(joined.map);
    } catch (error) {
        console.error(error);
        alert(error.message || "Could not start the game.");
        window.location.href = "/room_page";
        return;
    }

    const renderer = createRenderer(document.getElementById("gameCanvas"));
    const remotePlayers = getRemotePlayers();

    initTouchControls();

    function frame() {
        const { dx, dy } = readMovement();
        if (dx !== 0 || dy !== 0) {
            moveWithCollision(localPlayer, map, dx, dy);
        }

        renderer.draw({ map, localPlayer, remotePlayers });

        requestAnimationFrame(frame);
    }

    frame();
}

start();
