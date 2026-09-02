/*
 * Input: keyboard (WASD / arrows, Shift to sprint) and the on-screen
 * joystick plus B button for touch.
 *
 * This module reports *intent* only — a direction and whether sprint is
 * held. It does not know the player's speed, the map, or how long the
 * frame was; the game loop turns that intent into a distance.
 */

import { JOYSTICK_DEADZONE } from "./config.js";

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

// Holding a key and then leaving the page would otherwise leave it stuck
// down, and the player walking into a wall forever on return.
window.addEventListener("blur", () => {
    for (const key of Object.keys(keys)) keys[key] = false;
    joystickSprinting = false;
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
    window.addEventListener("touchcancel", onDragEnd);
    window.addEventListener("mouseup", onDragEnd);

    const onSprintStart = (event) => {
        if (event.cancelable) event.preventDefault();
        joystickSprinting = true;
        sprintButton.classList.add("is-held");
    };
    const onSprintEnd = () => {
        joystickSprinting = false;
        sprintButton.classList.remove("is-held");
    };

    sprintButton.addEventListener("touchstart", onSprintStart, { passive: false });
    sprintButton.addEventListener("mousedown", onSprintStart);
    sprintButton.addEventListener("touchend", onSprintEnd);
    sprintButton.addEventListener("touchcancel", onSprintEnd);
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
 * Where the player wants to go, as a vector no longer than 1, plus
 * whether sprint is held. A partly tilted joystick gives a shorter
 * vector, so it moves proportionally slower.
 */
export function readInput() {
    const sprinting = isDown("shift") || joystickSprinting;

    if (Math.abs(joystick.x) > JOYSTICK_DEADZONE ||
        Math.abs(joystick.y) > JOYSTICK_DEADZONE) {
        return { x: joystick.x, y: joystick.y, sprinting };
    }

    let x = 0;
    let y = 0;

    if (isDown("w", "arrowup")) y -= 1;
    if (isDown("s", "arrowdown")) y += 1;
    if (isDown("a", "arrowleft")) x -= 1;
    if (isDown("d", "arrowright")) x += 1;

    // Normalise, or holding two keys would move you diagonally about 1.41
    // times faster than in a straight line.
    const length = Math.hypot(x, y);
    if (length > 1) {
        x /= length;
        y /= length;
    }

    return { x, y, sprinting };
}
