/*
 * Loading map data.
 *
 * Maps are plain JSON: a size, rooms for labels and floor tone, wall
 * rectangles, furniture, base zones and spawn points. Everything derived
 * from them is worked out once here rather than per frame.
 */

export async function loadMap(mapName) {
    const response = await fetch(`/static/maps/${mapName}.json`);

    if (!response.ok) {
        throw new Error(`Failed to load map "${mapName}": ${response.status}`);
    }

    return prepare(await response.json());
}

/*
 * Split furniture by what it does, and precompute the base centre.
 *
 * Solid furniture is collidable and joins the wall list that physics
 * walks; hiding spots and decor are walked over, so they must not.
 */
function prepare(map) {
    const furniture = map.furniture ?? [];

    map.rooms ??= [];
    map.base_zones ??= [];
    map.doorways ??= [];

    // Which way a window throws its light: inwards, away from whichever
    // edge of the house it is set into.
    map.windows = (map.windows ?? []).map((win) => ({
        ...win,
        into: win.y <= 0 ? "down"
            : win.y + win.h >= map.height ? "up"
            : win.x <= 0 ? "right"
            : "left",
    }));

    map.hideSpots = furniture.filter((item) => item.hide);
    map.decor = furniture.filter((item) => !item.hide && !item.solid);
    map.solidFurniture = furniture.filter((item) => item.solid);

    // What the player is actually stopped by.
    map.obstacles = [...map.walls, ...map.solidFurniture];

    const base = map.base_zones[0];
    map.baseCenter = base
        ? { x: base.x + base.w / 2, y: base.y + base.h / 2 }
        : { x: map.width / 2, y: map.height / 2 };

    return map;
}

/* The hiding spot a point is inside, or null. Uses the player's centre,
 * so half a foot out of the wardrobe does not count — same rule the
 * server applies in maps.hiding_spot_at. */
export function hideSpotAt(map, x, y) {
    return map.hideSpots.find(
        (spot) => x >= spot.x && x <= spot.x + spot.w
            && y >= spot.y && y <= spot.y + spot.h,
    ) ?? null;
}

/* Is a point inside a base zone? */
export function inBase(map, x, y) {
    return map.base_zones.some(
        (zone) => x >= zone.x && x <= zone.x + zone.w
            && y >= zone.y && y <= zone.y + zone.h,
    );
}
