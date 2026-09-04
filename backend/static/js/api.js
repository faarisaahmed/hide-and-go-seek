/*
 * Thin wrappers over the server's JSON endpoints.
 *
 * All paths are relative, so the client always talks to whichever host
 * served the page. That is what makes LAN play work: a phone opening
 * http://192.168.x.x:5000 hits that same address, with nothing hardcoded.
 */

async function postJSON(path, body) {
    const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    return response.json();
}

export function createRoom(name) {
    return postJSON("/create_room", { name });
}

export function joinRoom(code, name) {
    return postJSON("/join_room", { code, name });
}

/* Returns the room's { players, chat }, or null if it no longer exists. */
export async function fetchRoom(code) {
    const response = await fetch(`/room/${code}`);
    if (!response.ok) return null;
    return response.json();
}

export function changeEmoji(code, name, emoji) {
    return postJSON("/change_emoji", { code, name, emoji });
}

export function setMode(code, name, mode) {
    return postJSON("/set_mode", { code, name, mode });
}

export function sendChat(code, name, message) {
    return postJSON("/send_chat", { code, name, message });
}
