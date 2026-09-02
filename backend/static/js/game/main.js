/*
 * Game entrypoint (/game_page).
 *
 * Owns the local player and the frame loop, and hands the other modules
 * what they need: input reports intent, physics resolves it against the
 * map, network syncs it, renderer draws the result.
 */

import { requireSession } from "../session.js";
import {
    MAX_FRAME_SECONDS,
    PLAYER_SIZE,
    PLAYER_SPEED,
    SPRINT_MULTIPLIER,
} from "./config.js";
import { initTouchControls, readInput } from "./input.js";
import { loadMap } from "./map_loader.js";
import { getRemotePlayers, join } from "./network.js";
import { moveWithCollision } from "./physics.js";
import { createRenderer } from "./renderer.js";

const els = {
    canvas: document.getElementById("gameCanvas"),
    name: document.getElementById("hudName"),
    count: document.getElementById("hudCount"),
    banner: document.getElementById("connectionBanner"),
};

async function start() {
    const session = requireSession();
    if (!session) return;

    els.name.textContent = session.name;

    // Position and emoji are filled in by the server, which decides where
    // everyone spawns.
    const localPlayer = {
        x: 0,
        y: 0,
        size: PLAYER_SIZE,
        name: session.name,
        emoji: "",
    };

    let map;
    let socket;
    try {
        const joined = await join({
            code: session.code,
            name: session.name,
            localPlayer,
        });
        socket = joined.socket;
        map = await loadMap(joined.map);
    } catch (error) {
        console.error(error);
        alert(error.message || "Could not start the game.");
        window.location.href = "/room_page";
        return;
    }

    // Say so rather than just freezing if the connection drops.
    socket.on("disconnect", () => { els.banner.hidden = false; });
    socket.on("connect", () => { els.banner.hidden = true; });

    const renderer = createRenderer(els.canvas);
    const remotePlayers = getRemotePlayers();

    initTouchControls();

    let lastFrame = performance.now();

    function frame(now) {
        // Seconds since the last frame, so movement is the same speed on
        // a 60Hz laptop and a 120Hz phone. Clamped so returning to a
        // backgrounded tab does not jump the player across the map.
        const dt = Math.min((now - lastFrame) / 1000, MAX_FRAME_SECONDS);
        lastFrame = now;

        const { x, y, sprinting } = readInput();
        if (x !== 0 || y !== 0) {
            const distance = PLAYER_SPEED * (sprinting ? SPRINT_MULTIPLIER : 1) * dt;
            moveWithCollision(localPlayer, map, x * distance, y * distance);
        }

        renderer.draw({ map, localPlayer, remotePlayers });

        els.count.textContent = Object.keys(remotePlayers).length + 1;

        requestAnimationFrame(frame);
    }

    requestAnimationFrame(frame);
}

start();
