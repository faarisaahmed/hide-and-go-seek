/*
 * Collision with the house.
 *
 * Axis-at-a-time resolution: move on X, push back out of anything we
 * ended up inside, then repeat for Y. Doing the axes separately is what
 * lets a player slide along a wall instead of sticking to it.
 *
 * "Obstacles" are the walls plus the solid furniture, worked out once by
 * the map loader. Hiding spots are deliberately not in that list: you
 * have to be able to walk into a wardrobe to hide in it.
 */

function overlaps(a, b) {
    return (
        a.x < b.x + b.w &&
        a.x + a.w > b.x &&
        a.y < b.y + b.h &&
        a.y + a.h > b.y
    );
}

export function moveWithCollision(player, map, dx, dy) {
    const box = { x: player.x, y: player.y, w: player.size, h: player.size };

    player.x += dx;
    box.x = player.x;

    for (const wall of map.obstacles) {
        if (!overlaps(box, wall)) continue;

        // Snap to whichever face of the obstacle we came from.
        if (dx > 0) player.x = wall.x - player.size;
        else if (dx < 0) player.x = wall.x + wall.w;

        box.x = player.x;
    }

    player.y += dy;
    box.y = player.y;

    for (const wall of map.obstacles) {
        if (!overlaps(box, wall)) continue;

        if (dy > 0) player.y = wall.y - player.size;
        else if (dy < 0) player.y = wall.y + wall.h;

        box.y = player.y;
    }
}
