/*
 * The landing page: pick a name, then create or join a room.
 */

import { createRoom, joinRoom } from "./api.js";
import { saveSession } from "./session.js";

const els = {
    name: document.getElementById("displayName"),
    code: document.getElementById("roomCodeInput"),
    create: document.getElementById("createRoomButton"),
    join: document.getElementById("joinRoomButton"),
    message: document.getElementById("messageBox"),
};

function showError(text) {
    els.message.textContent = text;
}

/* Read the name field, complaining inline if it is blank. */
function readDisplayName() {
    const name = els.name.value.trim();
    if (!name) {
        showError("Pick a name first.");
        els.name.focus();
        return null;
    }
    return name;
}

/* Store our identity and move on to the lobby. */
function enterRoom(code, name) {
    saveSession(code, name);
    window.location.href = "/room_page";
}

/*
 * Run a request with the buttons disabled, so an impatient double tap
 * cannot create two rooms.
 */
async function withButtonsDisabled(work) {
    els.create.disabled = true;
    els.join.disabled = true;
    showError("");

    try {
        await work();
    } catch (error) {
        console.error(error);
        showError("Could not reach the server.");
    } finally {
        els.create.disabled = false;
        els.join.disabled = false;
    }
}

function onCreateRoom() {
    const name = readDisplayName();
    if (!name) return;

    return withButtonsDisabled(async () => {
        const data = await createRoom(name);
        if (!data.success) {
            showError(data.message || "Could not create a room.");
            return;
        }
        enterRoom(data.room_code, name);
    });
}

function onJoinRoom() {
    const name = readDisplayName();
    if (!name) return;

    const code = els.code.value.trim();
    if (!/^[0-9]{4}$/.test(code)) {
        showError("Room codes are 4 digits.");
        els.code.focus();
        return;
    }

    return withButtonsDisabled(async () => {
        const data = await joinRoom(code, name);
        if (!data.success) {
            // The server explains why: no such room, or the name is taken.
            showError(data.message || "Could not join that room.");
            return;
        }
        enterRoom(code, name);
    });
}

els.create.addEventListener("click", onCreateRoom);
els.join.addEventListener("click", onJoinRoom);

// Typing again means they are fixing the problem; clear the complaint.
for (const input of [els.name, els.code]) {
    input.addEventListener("input", () => showError(""));
}

// Enter submits whichever field makes sense.
els.name.addEventListener("keydown", (e) => {
    if (e.key === "Enter") onCreateRoom();
});
els.code.addEventListener("keydown", (e) => {
    if (e.key === "Enter") onJoinRoom();
});

els.name.focus();
