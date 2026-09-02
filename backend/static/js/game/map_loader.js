/*
 * Loading map data. Maps are plain JSON: a size, a list of wall
 * rectangles, and optional base_zones / spawn_points.
 */

export async function loadMap(mapName) {
    const response = await fetch(`/static/maps/${mapName}.json`);

    if (!response.ok) {
        throw new Error(`Failed to load map "${mapName}": ${response.status}`);
    }

    return response.json();
}
