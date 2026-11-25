import assert from "node:assert/strict";
import test from "node:test";

test("proxy opt-in conserva las barras Django y no cambia la ejecución local habitual", async () => {
  const previous = process.env.OPERIX_API_PROXY_TARGET;
  try {
    delete process.env.OPERIX_API_PROXY_TARGET;
    const { default: local } = await import("../next.config.ts?test=local");
    assert.equal(local.rewrites, undefined);
    assert.equal(local.experimental, undefined);
    process.env.OPERIX_API_PROXY_TARGET = "http://127.0.0.1:18000/";
    const { default: remote } = await import("../next.config.ts?test=remote");
    assert.deepEqual(await remote.rewrites(), {
      fallback: [
        {
          source: "/api/v1/:path*",
          destination: "http://127.0.0.1:18000/api/v1/:path*/",
        },
      ],
    });
    assert.equal(remote.skipTrailingSlashRedirect, true);
    assert.equal(remote.experimental.proxyClientMaxBodySize, "251mb");
  } finally {
    if (previous === undefined) delete process.env.OPERIX_API_PROXY_TARGET;
    else process.env.OPERIX_API_PROXY_TARGET = previous;
  }
});
