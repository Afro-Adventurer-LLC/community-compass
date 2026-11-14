// Runs before `next build`. The static export bakes the ABW API base into the bundle, so the
// build must be told which API to use. The deploy workflow sets it from Terraform; locally,
// see .env.example. Fails instead of silently building a site whose chat has no API.
const base = process.env.NEXT_PUBLIC_ABW_API_BASE || "";
if (!base) {
  console.error("NEXT_PUBLIC_ABW_API_BASE is not set. The static export needs the ABW API base URL at build time.");
  process.exit(1);
}
if (!/^https?:\/\//.test(base)) {
  console.error("NEXT_PUBLIC_ABW_API_BASE must be an absolute http(s) URL for a static export (a /abw-api proxy path only works in `next dev`).");
  process.exit(1);
}
console.log("ABW API base is set for this build.");
