import assert from "node:assert/strict";
import test from "node:test";

const sessionUrl = "/api/v1/auth/session/";
const controlUrl = "/api/v1/analysis/cameras/control/";
const user = { username: "fixture-admin", role: "administrator" };
const session = (account) =>
  Response.json({ user: account, csrf_token: "TEST_ONLY_CSRF" });

async function setup(t, handleFetch) {
  const auth = await import(`../src/services/browser-session.ts?${t.name}`);
  const events = new EventTarget();
  const expired = t.mock.fn();
  events.addEventListener(auth.sessionExpired, expired);
  globalThis.window = events;
  t.after(() => delete globalThis.window);
  const fetch = t.mock.method(globalThis, "fetch", handleFetch);
  return { ...auth, expired, fetch };
}

test("lab activation failures stay local and the PATCH is never replayed", async (t) => {
  const { apiFetch, expired, fetch } = await setup(t, async (url, init) => {
    if (url === sessionUrl) return session(user);
    assert.equal(url, controlUrl);
    assert.equal(init.method, "PATCH");
    assert.equal(init.headers.get("X-CSRFToken"), "TEST_ONLY_CSRF");
    return new Response("Bad gateway", { status: 502 });
  });

  const response = await apiFetch(controlUrl, {
    method: "PATCH",
    body: '{"enabled":true}',
  });
  assert.equal(response.status, 502);
  assert.equal(fetch.mock.callCount(), 2);
  assert.equal(expired.mock.callCount(), 0);
});

test("unconfirmed 401s are retryable and a later request can recover", async (t) => {
  for (const [name, probe] of [
    ["authenticated", () => session(user)],
    ["gateway failure", () => new Response("Unavailable", { status: 503 })],
    [
      "network failure",
      () => {
        throw new TypeError("Failed to fetch");
      },
    ],
    [
      "timeout",
      () => {
        throw new DOMException("Timed out", "TimeoutError");
      },
    ],
    ["HTML", () => new Response("<html>Proxy error</html>")],
    ["missing identity", () => Response.json({ csrf_token: "TEST_ONLY_CSRF" })],
    ["invalid identity", () => session({ ...user, role: "unknown" })],
  ]) {
    await t.test(name, async (t) => {
      let reads = 0;
      const { apiFetch, expired, fetch } = await setup(t, async (url) => {
        if (url === sessionUrl) return probe();
        return new Response(null, { status: ++reads === 1 ? 401 : 200 });
      });

      await assert.rejects(apiFetch(controlUrl), /Intenta de nuevo/);
      assert.equal(expired.mock.callCount(), 0);
      assert.equal((await apiFetch(controlUrl)).status, 200);
      assert.deepEqual(
        fetch.mock.calls.map(({ arguments: [url] }) => url),
        [controlUrl, sessionUrl, controlUrl],
      );
    });
  }
});

test("concurrent 401s share a session check and report confirmed expiration once", async (t) => {
  const probe = Promise.withResolvers();
  const started = Promise.withResolvers();
  const { apiFetch, expired, fetch } = await setup(t, async (url) => {
    if (url !== sessionUrl) return new Response(null, { status: 401 });
    started.resolve();
    return probe.promise;
  });

  const requests = Promise.allSettled([
    apiFetch(controlUrl),
    apiFetch(controlUrl),
  ]);
  await started.promise;
  assert.equal(expired.mock.callCount(), 0);
  probe.resolve(session(null));
  const results = await requests;
  assert.ok(
    results.some(
      (result) => result.status === "fulfilled" && result.value.status === 401,
    ),
  );
  assert.equal(
    fetch.mock.calls.filter(({ arguments: [url] }) => url === sessionUrl)
      .length,
    1,
  );
  assert.equal(expired.mock.callCount(), 1);
});

test("a stale anonymous response cannot expire a newly signed-in account", async (t) => {
  const probe = Promise.withResolvers();
  const started = Promise.withResolvers();
  let reads = 0;
  const { apiFetch, signIn, getSession, expired } = await setup(
    t,
    async (url) => {
      if (url === sessionUrl) {
        if (++reads !== 2) return session(user);
        started.resolve();
        return probe.promise;
      }
      if (url === "/api/v1/auth/login/") return session(user);
      return new Response(null, { status: 401 });
    },
  );

  await getSession();
  const request = assert.rejects(apiFetch(controlUrl), /Intenta de nuevo/);
  await started.promise;
  assert.deepEqual(await signIn(user.username, "TEST_ONLY_PASSWORD"), user);
  assert.deepEqual(await getSession(), user);
  probe.resolve(session(null));
  await request;
  assert.equal(expired.mock.callCount(), 0);
});

test("aborting a lab request releases its waiter and leaves the shared check running", async (t) => {
  const probe = Promise.withResolvers();
  const started = Promise.withResolvers();
  const { apiFetch, getSession, expired } = await setup(t, async (url) => {
    if (url !== sessionUrl) return new Response(null, { status: 401 });
    started.resolve();
    return probe.promise;
  });

  const controller = new AbortController();
  const request = assert.rejects(
    apiFetch(controlUrl, { signal: controller.signal }),
    { name: "AbortError" },
  );
  await started.promise;
  const shared = getSession();
  controller.abort();
  await request;
  probe.resolve(session(user));
  assert.deepEqual(await shared, user);
  assert.equal(expired.mock.callCount(), 0);
});
