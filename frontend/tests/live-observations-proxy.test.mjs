import assert from "node:assert/strict";
import { createServer } from "node:http";
import test from "node:test";

import { GET } from "../src/app/api/v1/analysis/cameras/[id]/live/observations/route.ts";

test("proxy de overlays recupera un reset y conserva autenticación, cursor y estados HTTP", async (t) => {
  const attempts = [];
  let behavior = "recover";
  const backend = createServer((req, res) => {
    attempts.push({ url: req.url, cookie: req.headers.cookie });
    if (
      behavior === "down" ||
      (behavior === "recover" && attempts.length === 1)
    ) {
      req.socket.destroy();
      return;
    }
    if (behavior === "timeout") return;
    const status = behavior === "recover" ? 200 : Number(behavior);
    res.writeHead(status, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ run_id: "current-run", items: [] }));
  });
  await new Promise((resolve) => backend.listen(0, "127.0.0.1", resolve));
  t.after(() => {
    backend.closeAllConnections();
    backend.close();
  });
  const old = process.env.OPERIX_API_PROXY_TARGET;
  process.env.OPERIX_API_PROXY_TARGET =
    "http://127.0.0.1:" + backend.address().port;
  t.after(() => {
    if (old === undefined) delete process.env.OPERIX_API_PROXY_TARGET;
    else process.env.OPERIX_API_PROXY_TARGET = old;
  });
  const path =
    "/api/v1/analysis/cameras/lab-cam-02/live/observations/?after=8&run_id=current-run";
  const read = () =>
    GET(
      new Request("http://operix.test" + path, {
        headers: { cookie: "sessionid=fixture-only" },
      }),
      { params: Promise.resolve({ id: "lab-cam-02" }) },
    );

  const ok = await read();
  assert.deepEqual(await ok.json(), { run_id: "current-run", items: [] });
  assert.equal(ok.headers.get("cache-control"), "private, no-store");
  assert.deepEqual(
    attempts,
    Array(2).fill({ url: path, cookie: "sessionid=fixture-only" }),
  );

  for (const status of [204, 401, 403, 404, 500]) {
    behavior = String(status);
    attempts.length = 0;
    const reply = await read();
    assert.equal(reply.status, status);
    assert.equal(attempts.length, 1);
    if (status === 204) assert.equal(await reply.text(), "");
  }

  behavior = "down";
  attempts.length = 0;
  assert.equal((await read()).status, 502);
  assert.equal(attempts.length, 2);

  behavior = "timeout";
  attempts.length = 0;
  assert.equal((await read()).status, 504);
  assert.equal(attempts.length, 1);
});
