// Where the data bundle and the live gateway are, so the same build runs at the site root in development and
// under a subpath on coszo.org (coszo.org/rca-atlas/map/). BASE_URL is "/" in dev and tests, "./" in a build.
export const atlasUrl = path => `${import.meta.env.BASE_URL}atlas/${path}`;
// The gateway: Vite proxies /api to it in development. A static host has none unless VITE_ATLAS_GATEWAY points at one;
// without it the live sections say the service is not running and the rest of the map works.
export const GATEWAY = import.meta.env.VITE_ATLAS_GATEWAY || "/api";
