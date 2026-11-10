/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async redirects() {
    return [{ source: "/report", destination: "/notes", permanent: true }];
  },
};

export default nextConfig;
