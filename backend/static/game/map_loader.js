/*
map_loader.js
Responsible only for loading map JSON data.
Does NOT handle rendering or movement.
*/

let GameMap = null;

/*
Load map JSON file from server
Example: loadMap("house1")
*/
async function loadMap(mapName) {

    try {

        let response = await fetch(`/static/game/maps/${mapName}.json`);

        if (!response.ok) {
            console.error("Failed to load map:", mapName);
            return null;
        }

        GameMap = await response.json();

        console.log("Map loaded:", mapName);

        return GameMap;

    } catch (err) {
        console.error("Map loading error:", err);
        return null;
    }
}

/*
Get map data after loading
*/
function getMap() {
    return GameMap;
}

/*
Check if map is loaded
*/
function isMapLoaded() {
    return GameMap !== null;
}