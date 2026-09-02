/*
 * Input: keyboard (WASD / arrows, Shift to sprint) and the on-screen
 * joystick plus B button for touch.
 *
 * This module only reports intent. It does not touch the player or the
 * map — the game loop asks for a movement vector and decides what to do
 * with it.
 */

import { JOYSTICK_DEADZONE, PLAYER_SPEED, SPRINT_MULTIPLIER } from "./config.js";

const keys = {};

const joystick = { x: 0, y: 0 };
let joystickSprinting = false;

/* =========================
 * Keyboard
 * ========================= */

window.addEventListener("keydown", (event) => {
    keys[event.key.toLowerCase()] = true;
});

window.addEventListener("keyup", (event) => {
    keys[event.key.toLowerCase()] = false;
});

/* =========================
 * Touch controls
 * ========================= */

export function initTouchControls() {
    const pad = document.getElementById("joystick");
    const knob = document.getElementById("stick");
    const sprintButton = document.getElementById("btnB");

    let dragging = false;

    const onDragMove = (event) => {
        if (!dragging) return;
        if (event.cancelable) event.preventDefault();

        const pointer = event.touches ? event.touches[0] : event;
        const bounds = pad.getBoundingClientRect();
        const radius = bounds.width / 2;

        let dx = pointer.clientX - (bounds.left + radius);
        let dy = pointer.clientY - (bounds.top + bounds.height / 2);

        // Clamp the knob to the edge of the pad, keeping its direction.
        const distance = Math.hypot(dx, dy);
        if (distance > radius) {
            dx *= radius / distance;
            dy *= radius / distance;
        }

        knob.style.transform = `translate3d(${dx}px, ${dy}px, 0)`;

        joystick.x = dx / radius;
        joystick.y = dy / radius;
    };

    const onDragStart = (event) => {
        dragging = true;
        onDragMove(event);
    };

    const onDragEnd = () => {
        dragging = false;
        joystick.x = 0;
        joystick.y = 0;
        knob.style.transform = "translate3d(0, 0, 0)";
    };

    pad.addEventListener("touchstart", onDragStart, { passive: false });
    pad.addEventListener("mousedown", onDragStart);

    // Tracked on window, not the pad, so a thumb that slides off the pad
    // keeps steering instead of the knob freezing.
    window.addEventListener("touchmove", onDragMove, { passive: false });
    window.addEventListener("mousemove", onDragMove);
    window.addEventListener("touchend", onDragEnd);
    window.addEventListener("mouseup", onDragEnd);

    const onSprintStart = (event) => {
        if (event.cancelable) event.preventDefault();
        joystickSprinting = true;
    };
    const onSprintEnd = () => {
        joystickSprinting = false;
    };

    sprintButton.addEventListener("touchstart", onSprintStart, { passive: false });
    sprintButton.addEventListener("mousedown", onSprintStart);
    sprintButton.addEventListener("touchend", onSprintEnd);
    sprintButton.addEventListener("mouseup", onSprintEnd);
    sprintButton.addEventListener("mouseleave", onSprintEnd);
}

/* =========================
 * Reading input
 * ========================= */

function isDown(...names) {
    return names.some((name) => keys[name]);
}

/*
 * The movement the player is asking for this frame, in pixels.
 * The joystick takes priority when it is off centre.
 */
export function readMovement() {
    const speed = isDown("shift") || joystickSprinting
        ? PLAYER_SPEED * SPRINT_MULTIPLIER
        : PLAYER_SPEED;

    if (Math.abs(joystick.x) > JOYSTICK_DEADZONE || Math.abs(joystick.y) > JOYSTICK_DEADZONE) {
        return { dx: joystick.x * speed, dy: joystick.y * speed };
    }

    let dx = 0;
    let dy = 0;

    if (isDown("w", "arrowup")) dy -= speed;
    if (isDown("s", "arrowdown")) dy += speed;
    if (isDown("a", "arrowleft")) dx -= speed;
    if (isDown("d", "arrowright")) dx += speed;

    return { dx, dy };
}
