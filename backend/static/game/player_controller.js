/*
player_controller.js
Handles keyboard + mobile joystick + Switch-style ABXY input.
*/

let keys = {};
let playerSpeed = 10;
let sprintMultiplier = 1.5;

// Mobile State
let joystickVector = { x: 0, y: 0 };
let isSprinting = false;

if (!window.player) {
    window.player = { x: 100, y: 100, size: 40 };
}

/* =============================
Keyboard Input
============================= */
window.addEventListener("keydown", e => { keys[e.key.toLowerCase()] = true; });
window.addEventListener("keyup", e => { keys[e.key.toLowerCase()] = false; });

/* =============================
Mobile Control Logic
============================= */
function initMobileControls() {
    const knob = document.getElementById('stick'); 
    const boundary = document.getElementById('joystick');
    const btnB = document.getElementById('btnB');

    if (!knob || !boundary) {
        setTimeout(initMobileControls, 100);
        return;
    }

    let isDragging = false;

    const handleMove = (e) => {
        if (!isDragging) return;
        if (e.cancelable) e.preventDefault();

        const pointer = e.touches ? e.touches[0] : e;
        const rect = boundary.getBoundingClientRect();
        
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;

        let dx = pointer.clientX - centerX;
        let dy = pointer.clientY - centerY;
        
        const distance = Math.sqrt(dx * dx + dy * dy);
        const maxRadius = rect.width / 2;

        if (distance > maxRadius) {
            dx *= maxRadius / distance;
            dy *= maxRadius / distance;
        }

        knob.style.transform = `translate3d(${dx}px, ${dy}px, 0)`;

        joystickVector.x = dx / maxRadius;
        joystickVector.y = dy / maxRadius;
    };

    const startMove = (e) => {
        isDragging = true;
        handleMove(e);
    };

    const stopMove = () => {
        isDragging = false;
        joystickVector = { x: 0, y: 0 };
        knob.style.transform = `translate3d(0, 0, 0)`;
    };

    boundary.addEventListener("touchstart", startMove, { passive: false });
    boundary.addEventListener("mousedown", startMove);
    window.addEventListener("touchmove", handleMove, { passive: false });
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("touchend", stopMove);
    window.addEventListener("mouseup", stopMove);

    if (btnB) {
        const startSprint = (e) => {
            if (e.cancelable) e.preventDefault();
            isSprinting = true;
        };
        const endSprint = () => { isSprinting = false; };

        btnB.addEventListener("touchstart", startSprint, { passive: false });
        btnB.addEventListener("mousedown", startSprint);
        btnB.addEventListener("touchend", endSprint);
        btnB.addEventListener("mouseup", endSprint);
        btnB.addEventListener("mouseleave", endSprint);
    }
}

/* =============================
Movement Update Loop
============================= */
function updatePlayerMovement() {
    let currentSpeed = playerSpeed;

    if (keys["shift"] || isSprinting) {
        currentSpeed *= sprintMultiplier;
    }

    let dx = 0;
    let dy = 0;

    if (keys["w"] || keys["arrowup"]) dy -= currentSpeed;
    if (keys["s"] || keys["arrowdown"]) dy += currentSpeed;
    if (keys["a"] || keys["arrowleft"]) dx -= currentSpeed;
    if (keys["d"] || keys["arrowright"]) dx += currentSpeed;

    if (Math.abs(joystickVector.x) > 0.01 || Math.abs(joystickVector.y) > 0.01) {
        dx = joystickVector.x * currentSpeed;
        dy = joystickVector.y * currentSpeed;
    }

    if (dx !== 0 || dy !== 0) {
        if (typeof moveWithCollision === "function") {
            moveWithCollision(dx, dy);
        } else {
            window.player.x += dx;
            window.player.y += dy;
        }
    }
}

// --- NEW TICK RATE HEARTBEAT ---
// This sends data 60 times a second, independent of movement.
setInterval(() => {
    if (window.socket && window.player) {
        window.socket.emit("player_move", {
            x: window.player.x,
            y: window.player.y
        });
    }
}, 16); 

window.playerControllerUpdate = function() {
    updatePlayerMovement();
};

if (document.readyState === 'loading') {
    window.addEventListener('DOMContentLoaded', initMobileControls);
} else {
    initMobileControls();
}