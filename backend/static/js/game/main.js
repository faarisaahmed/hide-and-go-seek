/*
 * Game entrypoint (/game_page).
 *
 * Owns the local player and the frame loop, and hands the other modules
 * what they need: input reports intent, physics resolves it against the
 * map, network syncs it, renderer draws the result.
 */

import { requireSession } from "../session.js";
import { DEFAULT_MAP, PLAYER_SIZE, SPAWN_X, SPAWN_Y } from "./config.js";
import { initTouchControls, readMovement } from "./input.js";
import { loadMap } from "./map_loader.js";
import { connect, getRemotePlayers } from "./network.js";
import { moveWithCollision } from "./physics.js";
import { createRenderer } from "./renderer.js";

async function start() {
    const session = requireSession();
    if (!session) return;

    const localPlayer = { x: SPAWN_X, y: SPAWN_Y, size: PLAYER_SIZE };

    let map;
    try {
        map = await loadMap(DEFAULT_MAP);
    } catch (error) {
        console.error(error);
        alert("Could not load the map.");
        return;
    }

    const renderer = createRenderer(document.getElementById("gameCanvas"));
    const remotePlayers = getRemotePlayers();

    initTouchControls();
    connect({ code: session.code, name: session.name, localPlayer });

    function frame() {
        const { dx, dy } = readMovement();
        if (dx !== 0 || dy !== 0) {
            moveWithCollision(localPlayer, map, dx, dy);
        }

        renderer.draw({
            map,
            localPlayer,
            localName: session.name,
            remotePlayers,
        });

        requestAnimationFrame(frame);
    }

    frame();
}

start();
