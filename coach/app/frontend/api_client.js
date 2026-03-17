// coach/app/frontend/api_client.js

// -----------------------------
// CONFIG
// -----------------------------

// Set this to true when served from Shopify
const STATIC_MODE = false;

// Shopify base URL where racepacks are hosted
// EXAMPLE:
// https://your-store.myshopify.com/cdn/racepacks
const STATIC_BASE = "http://localhost:9000/racepacks";


// -----------------------------
// API GET
// -----------------------------
export async function apiGet(path) {
  const url = STATIC_MODE ? mapStaticPath(path) : path;

  const res = await fetch(url, {
    headers: { "Accept": "application/json" },
  });

  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${txt}`);
  }

  return await res.json();
}

// -----------------------------
// PATH MAPPER
// -----------------------------
function mapStaticPath(path) {
  // /api/races
  if (path === "/api/races") {
    return `${STATIC_BASE}/_index/races_index.json`;
  }

  // /api/races/{id}/info
  const raceInfo = path.match(/^\/api\/races\/([^/]+)\/info$/);
  if (raceInfo) {
    return `${STATIC_BASE}/${raceInfo[1]}/info.json`;
  }

  // /api/geometry?race_id=XYZ
  const geom = path.match(/^\/api\/geometry\?race_id=([^&]+)/);
  if (geom) {
    return `${STATIC_BASE}/${geom[1]}/geometry.json`;
  }

  // /api/races/{id}/track?sailor=x&leg=y
  const track = path.match(/^\/api\/races\/([^/]+)\/track\?(.+)$/);
  if (track) {
    const raceId = track[1];
    const params = new URLSearchParams(track[2]);
    const sailor = params.get("sailor");
    const leg = params.get("leg");

    if (!sailor) throw new Error("Missing sailor in track request");

    if (!leg || leg === "total") {
      return `${STATIC_BASE}/${raceId}/tracks/${sailor}.json`;
    }
    return `${STATIC_BASE}/${raceId}/tracks/${sailor}_leg${leg}.json`;
  }

  // /api/races/{id}/total_race_analytics
  const total = path.match(/^\/api\/races\/([^/]+)\/total_race_analytics$/);
  if (total) {
    return `${STATIC_BASE}/${total[1]}/total_race_analytics.json`;
  }

  // /api/leg_analytics?race_id=XYZ&leg=N
  const leg = path.match(/^\/api\/leg_analytics\?race_id=([^&]+)&leg=([^&]+)/);
  if (leg) {
    return `${STATIC_BASE}/${leg[1]}/leg_analytics/leg_${leg[2]}.json`;
  }

  // /api/races/{id}/slice?leg=N
  const slice = path.match(/^\/api\/races\/([^/]+)\/slice\?(.+)$/);
  if (slice) {
    const raceId = slice[1];
    const params = new URLSearchParams(slice[2]);
    const leg = params.get("leg");

    if (!leg || leg === "Total Race") {
      return `${STATIC_BASE}/${raceId}/slice/total.json`;
    }
    return `${STATIC_BASE}/${raceId}/slice/leg_${leg}.json`;
  }

  throw new Error(`No static mapping for API path: ${path}`);
}
