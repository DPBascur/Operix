import type { NextConfig } from "next";

// Opt-in: destino privado del servidor, nunca una dirección usada por el navegador.
const apiProxyTarget = process.env.OPERIX_API_PROXY_TARGET?.replace(/\/$/, "");

const nextConfig: NextConfig = {
  agentRules: false,
  output: "standalone",
  ...(apiProxyTarget
    ? {
        skipTrailingSlashRedirect: true,
        experimental: { proxyClientMaxBodySize: "251mb", proxyTimeout: 120000 },
        async rewrites() {
          return {
            fallback: [
              {
                source: "/api/v1/:path*",
                destination: `${apiProxyTarget}/api/v1/:path*/`,
              },
            ],
          };
        },
      }
    : {}),
};

export default nextConfig;
