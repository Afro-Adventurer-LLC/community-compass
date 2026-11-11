/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Amplify Hosting serves the static export in frontend/out.
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
