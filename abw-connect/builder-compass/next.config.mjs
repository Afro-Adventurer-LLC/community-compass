import { PHASE_DEVELOPMENT_SERVER } from "next/constants.js";

// `next build` produces a static export (out/) that the deploy workflow zips and uploads to Amplify.
// `trailingSlash: true` makes every page a folder with an index.html (ask/index.html,
// session/<id>/index.html), which Amplify serves as clean URLs without rewrite rules.
//
// The ABW API base is NOT in this repo. It is read at build time from NEXT_PUBLIC_ABW_API_BASE,
// which the deploy workflow sets from the Terraform output of the environment it deploys
// (`npm run build` refuses to start without it, see scripts/check-build-env.mjs).
//
// `next dev` can proxy /abw-api/* to a deployed API (the API's CORS allows the Amplify origin,
// not always localhost). Set ABW_API_PROXY_TARGET in .env.local, see .env.example.

/** @param {string} phase */
export default function nextConfig(phase) {
  /** @type {import('next').NextConfig} */
  const config = {
    reactStrictMode: true,
    output: "export",
    trailingSlash: true,
    images: { unoptimized: true },
  };

  if (phase === PHASE_DEVELOPMENT_SERVER) {
    // A static export has no server, so these only apply to `next dev`. Amplify gets the
    // same /report redirect from a custom rule in infra/amplify.tf.
    delete config.output;
    const target = (process.env.ABW_API_PROXY_TARGET || "").replace(/\/$/, "");
    config.redirects = async () => [{ source: "/report", destination: "/notes", permanent: true }];
    if (target) {
      config.rewrites = async () => [{ source: "/abw-api/:path*", destination: `${target}/:path*` }];
    }
  }

  return config;
}
