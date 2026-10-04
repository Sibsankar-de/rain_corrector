/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  poweredByHeader: false,
  eslint: {
    // Lint runs as its own CI step so a build failure points at one cause.
    ignoreDuringBuilds: true
  },
  // Leaflet reaches for browser globals at module scope; keeping it out of the
  // server graph is what allows the map to be prerendered safely.
  transpilePackages: ["leaflet", "react-leaflet"]
};

export default nextConfig;
