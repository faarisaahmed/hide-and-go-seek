/*
 * Game entrypoint (/game_page).
 *
 * Owns the local player and the frame loop, and hands the other modules
 * what they need: input reports intent, physics resolves it against the
 * house, network syncs it, renderer and hud draw the result.
 *
 * The round itself is not decided here. Who is frozen, who is home and
 * which phase we are in all come from the server; this file reads that
 * state to decide whether to let the player move, and to draw.
 */

import { goHome, requireSession } from "../session.js";
import {
    MAX_FRAME_SECONDS,
    PLAYER_SIZE,
    PLAYER_SPEED,
    SPRINT_MULTIPLIER,
} from "./config.js";
import { drawHud, initHud, showProblem } from "./hud.js";
import { initTouchControls, readInput } from "./input.js";
import { loadMap } from "./map_loader.js";
import { getRemotePlayers, interpolateRemotes, join } from "./network.js";
import { moveWithCollision } from "./physics.js";
import { createRenderer } from "./renderer.js";
import { canMove, getRound, playerNamed } from "./round.js";
import { resetStamina, stepStamina } from "./stamina.js";

const els = {
    canvas: document.getElementById("gameCanvas"),
    banner: document.getElementById("connectionBanner"),
    controls: document.getElementById("controls"),
};

async function start() {
    const session = requireSession();
    if (!session) return;

    // Position and emoji are filled in by the server, which decides where
    // everyone spawns. Role and state are mirrored onto the record each
    // frame so the renderer does not have to look them up itself.
    const localPlayer = {
        x: 0,
        y: 0,
        size: PLAYER_SIZE,
        name: session.name,
        emoji: "",
        role: null,
        state: "free",
        // Which way we are pointing, in radians, from the last direction
        // we actually moved. Standing still keeps the last one, which is
        // what you want when a seeker stops to look down a corridor.
        facing: 0,
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

    // The host can start another round without going back to the lobby.
    socket.on("start_rejected", (data) => {
        showProblem(data.message || "Could not start a round.");
    });

    initHud({
        name: session.name,
        onPlayAgain: () => socket.emit("start_game_request", { code: session.code }),
        onLeave: goHome,
    });

    const renderer = createRenderer(els.canvas);
    const remotePlayers = getRemotePlayers();

    initTouchControls();

    let lastFrame = performance.now();
    let lastPhase = null;

    function frame(now) {
        // Seconds since the last frame, so movement is the same speed on
        // a 60Hz laptop and a 120Hz phone. Clamped so returning to a
        // backgrounded tab does not jump the player across the house.
        const dt = Math.min((now - lastFrame) / 1000, MAX_FRAME_SECONDS);
        lastFrame = now;

        const me = playerNamed(session.name);
        localPlayer.role = me?.role ?? null;
        localPlayer.state = me?.state ?? "free";

        // Everybody starts a round with a full bar.
        const phase = getRound().phase;
        if (phase !== lastPhase) {
            lastPhase = phase;
            resetStamina();
        }

        const allowed = canMove(localPlayer.role, localPlayer.state);
        const { x, y, sprinting } =
            allowed ? readInput() : { x: 0, y: 0, sprinting: false };

        // Stamina still recovers while you are stood still, frozen, or
        // counting, so the bar is always up to date when you can move.
        const running = stepStamina(dt, sprinting && (x !== 0 || y !== 0));

        if (x !== 0 || y !== 0) {
            // Before the move, and from the input rather than from where
            // we ended up: walking into a wall should not swing the torch
            // round to face along it.
            localPlayer.facing = Math.atan2(y, x);

            const distance = PLAYER_SPEED * (running ? SPRINT_MULTIPLIER : 1) * dt;
            moveWithCollision(localPlayer, map, x * distance, y * distance);
        }

        // Grey the thumb pad out when the round says you cannot move, so
        // a dead joystick looks deliberate rather than broken.
        els.controls.classList.toggle("is-locked", !allowed);

        // Everyone else is eased towards wherever the server last put
        // them, which is what keeps a connection from another city
        // looking like movement rather than teleporting.
        interpolateRemotes(dt);

        renderer.draw({ map, localPlayer, remotePlayers });
        drawHud({ map, localPlayer, myName: session.name });

        requestAnimationFrame(frame);
    }

    requestAnimationFrame(frame);
}

start();
