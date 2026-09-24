const R = 6371.0088;   // mean Earth radius, km
const rad = d => (d * Math.PI) / 180;

export function distanceKm(lon1, lat1, lon2, lat2) {
  const a = Math.sin(rad(lat2 - lat1) / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(rad(lon2 - lon1) / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
}

// Catalogued sites within `km` of a point, nearest first: [{ site, km }].
export function sitesNear(sites, lon, lat, km = 30) {
  return sites.map(site => ({ site, km: distanceKm(lon, lat, site.lon, site.lat) }))
    .filter(x => x.km <= km).sort((a, b) => a.km - b.km);
}
