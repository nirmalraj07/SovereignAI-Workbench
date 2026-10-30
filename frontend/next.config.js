/** @type {import('next').NextConfig} */
const withBundleAnalyzer = require("@next/bundle-analyzer")({
  enabled: process.env.ANALYZE === "true",
});

const nextConfig = {
  output: "standalone",
  env: {
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000",
    NEXT_PUBLIC_WS_BASE_URL: process.env.NEXT_PUBLIC_WS_BASE_URL || "ws://localhost:8000",
  },
  // lucide-react is the heaviest third-party dependency actually used in
  // this app (recharts was scaffolded in package.json but never imported
  // anywhere — removed; see docs/DEPLOYMENT.md "Frontend performance").
  // modularizeImports rewrites lucide-react's barrel import into per-icon
  // imports so unused icons never enter the bundle instead of relying on
  // tree-shaking to catch it after the fact.
  modularizeImports: {
    "lucide-react": {
      transform: "lucide-react/dist/esm/icons/{{kebabCase member}}",
      skipDefaultConversion: true,
    },
  },
};

module.exports = withBundleAnalyzer(nextConfig);
