// Local equirectangular projection. 1 unit = 1 km. North is -z.
export const LON0 = -127.15, LAT0 = 45.15;
export const KX = 111.32 * Math.cos((LAT0 * Math.PI) / 180), KZ = 111.13;
export const toX = lon => (lon - LON0) * KX;
export const toZ = lat => -(lat - LAT0) * KZ;
export const fromX = x => x / KX + LON0;
export const fromZ = z => -z / KZ + LAT0;
