/*
 * Who you are and which room you are in.
 *
 * Stored in sessionStorage rather than localStorage so that two tabs can
 * be two different players, and so closing the tab ends the session.
 */

const ROOM_KEY = "roomCode";
const NAME_KEY = "playerName";

export function getSession() {
    return {
        code: sessionStorage.getItem(ROOM_KEY),
        name: sessionStorage.getItem(NAME_KEY),
    };
}

export function saveSession(code, name) {
    // Wipe first: a stale name from a previous room would otherwise stick
    // around and be sent to the server.
    sessionStorage.clear();
    // Older versions of this game kept the same keys in localStorage.
    localStorage.clear();

    sessionStorage.setItem(ROOM_KEY, code);
    sessionStorage.setItem(NAME_KEY, name);
}

export function clearSession() {
    sessionStorage.removeItem(ROOM_KEY);
    sessionStorage.removeItem(NAME_KEY);
}

/*
 * Return the session, or send the player home if they do not have one
 * (someone opening /room_page directly, or after a refresh in a new tab).
 * Returns null when redirecting, so callers should bail out.
 */
export function requireSession() {
    const session = getSession();
    if (!session.code || !session.name) {
        window.location.href = "/";
        return null;
    }
    return session;
}

export function goHome() {
    clearSession();
    window.location.href = "/";
}
