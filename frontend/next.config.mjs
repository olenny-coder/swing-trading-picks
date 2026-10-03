/** @type {import('next').NextConfig} */
// Static export: `next build` emits a fully static site into ./out, which the
// FastAPI backend serves. This lets the whole app run as a SINGLE service on
// Render (frontend + API on one URL) with no Vercel and no Node server.
const nextConfig = {
  reactStrictMode: true,
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
