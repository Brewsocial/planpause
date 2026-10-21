/** @type {import('next').NextConfig} */
// Statischer Export: Die App läuft komplett im Browser und wird von Cloudflare als statische Dateien ausgeliefert.
const nextConfig = { reactStrictMode: true, output: "export", images: { unoptimized: true } };
export default nextConfig;
