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
 *
 * `extra` is for obstacles that exist only for some players in some
 * phases — today just the base, which is a wall to the seeker and open
 * floor to everybody else. Passed in rather than baked into the map,
 * because the map is the same house for all of them.
 */

function overlaps(a, b) {
    return (
        a.x < b.x + b.w &&
        a.x + a.w > b.x &&
        a.y < b.y + b.h &&
        a.y + a.h > b.y
    );
}

/* Push back out of anything we ended up inside, on one axis. */
function pushOut(player, box, obstacles, dx, dy) {
    for (const wall of obstacles) {
        if (!overlaps(box, wall)) continue;

        // Snap to whichever face of the obstacle we came from.
        if (dx > 0) player.x = wall.x - player.size;
        else if (dx < 0) player.x = wall.x + wall.w;
        else if (dy > 0) player.y = wall.y - player.size;
        else if (dy < 0) player.y = wall.y + wall.h;

        box.x = player.x;
        box.y = player.y;
    }
}

export function moveWithCollision(player, map, dx, dy, extra = null) {
    const box = { x: player.x, y: player.y, w: player.size, h: player.size };

    player.x += dx;
    box.x = player.x;
    pushOut(player, box, map.obstacles, dx, 0);
    if (extra) pushOut(player, box, extra, dx, 0);

    player.y += dy;
    box.y = player.y;
    pushOut(player, box, map.obstacles, 0, dy);
    if (extra) pushOut(player, box, extra, 0, dy);
}
