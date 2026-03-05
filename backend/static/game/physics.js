/*
physics.js
Handles wall collision detection.
*/

function checkCollision(rect1, rect2) {
    return (
        rect1.x < rect2.x + rect2.w &&
        rect1.x + rect1.w > rect2.x &&
        rect1.y < rect2.y + rect2.h &&
        rect1.y + rect1.h > rect2.y
    );
}

function moveWithCollision(dx, dy) {

    let map = getMap();
    if (!map) return;

    // Build a proper rectangle for the player
    let playerRect = {
        x: player.x,
        y: player.y,
        w: player.size,
        h: player.size
    };

    // Horizontal movement
    player.x += dx;
    playerRect.x = player.x;

    for (let wall of map.walls) {
        if (checkCollision(playerRect, wall)) {

            if (dx > 0) {
                player.x = wall.x - player.size;
            } else if (dx < 0) {
                player.x = wall.x + wall.w;
            }

            playerRect.x = player.x;
        }
    }

    // Vertical movement
    player.y += dy;
    playerRect.y = player.y;

    for (let wall of map.walls) {
        if (checkCollision(playerRect, wall)) {

            if (dy > 0) {
                player.y = wall.y - player.size;
            } else if (dy < 0) {
                player.y = wall.y + wall.h;
            }

            playerRect.y = player.y;
        }
    }
}

window.moveWithCollision = moveWithCollision;