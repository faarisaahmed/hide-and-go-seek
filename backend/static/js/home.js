/*
 * The landing page: pick a name, then create or join a room.
 */

import { createRoom, joinRoom } from "./api.js";
import { saveSession } from "./session.js";

/* Read the name field, complaining if it is blank. Returns null if so. */
function readDisplayName() {
    const name = document.getElementById("displayName").value.trim();
    if (!name) {
        alert("Please enter a username");
        return null;
    }
    return name;
}

/* Store our identity and move on to the lobby. */
function enterRoom(code, name) {
    saveSession(code, name);
    window.location.href = "/room_page";
}

async function onCreateRoom() {
    const name = readDisplayName();
    if (!name) return;

    try {
        const data = await createRoom(name);
        if (!data.success) {
            alert("Room creation failed");
            return;
        }
        enterRoom(data.room_code, name);
    } catch (error) {
        console.error("Error creating room:", error);
        alert("Could not connect to server.");
    }
}

async function onJoinRoom() {
    const name = readDisplayName();
    if (!name) return;

    const code = document.getElementById("roomCodeInput").value.trim();
    if (!/^[0-9]+$/.test(code)) {
        alert("Room code must be numbers only");
        return;
    }

    try {
        const data = await joinRoom(code, name);
        if (!data.success) {
            alert("Room not found or name already taken");
            return;
        }
        enterRoom(code, name);
    } catch (error) {
        console.error("Error joining room:", error);
        alert("Could not connect to server.");
    }
}

document.getElementById("createRoomButton").addEventListener("click", onCreateRoom);
document.getElementById("joinRoomButton").addEventListener("click", onJoinRoom);
