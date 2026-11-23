import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdtemp, rm } from "node:fs/promises";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { setTimeout as delay } from "node:timers/promises";

const { WebSocket } = createRequire(import.meta.url)("next/dist/compiled/ws");
const base = process.env.OPERIX_CAMERA_LAB_BROWSER_URL;
const api = process.env.OPERIX_CAMERA_LAB_FIXTURE_URL;
const executable =
  process.env.OPERIX_BROWSER_EXECUTABLE ??
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const route = "/admin/camera-lab";
const controlPath = "/api/v1/analysis/cameras/control/";
const cameraId = "lab-cam-01";

async function waitFor(check, label) {
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    if (await check()) return;
    await delay(100);
  }
  assert.fail(`Timed out waiting for ${label}`);
}

async function openBrowser(t) {
  const profile = await mkdtemp(path.join(tmpdir(), "operix-lab-edge-"));
  const child = spawn(
    executable,
    [
      "--headless=new",
      "--remote-debugging-port=0",
      `--user-data-dir=${profile}`,
      "--no-first-run",
      "--no-default-browser-check",
      "about:blank",
    ],
    { windowsHide: true, stdio: ["ignore", "ignore", "pipe"] },
  );
  const exited = new Promise((resolve) => child.once("close", resolve));
  let socket;
  t.after(async () => {
    socket?.close();
    child.kill();
    await Promise.race([exited, delay(3000, undefined, { ref: false })]);
    assert.equal(path.dirname(path.resolve(profile)), path.resolve(tmpdir()));
    assert.match(path.basename(profile), /^operix-lab-edge-/);
    await rm(profile, { recursive: true, force: true, maxRetries: 5 });
  });
  const port = await new Promise((resolve, reject) => {
    let output = "";
    const timer = setTimeout(
      () => reject(new Error("Edge did not start DevTools")),
      15_000,
    );
    child.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.stderr.on("data", (chunk) => {
      output += chunk;
      const match = output.match(/DevTools listening on ws:\/\/[^:]+:(\d+)/);
      if (match) {
        clearTimeout(timer);
        resolve(match[1]);
      }
    });
  });
  const targets = await fetch(`http://127.0.0.1:${port}/json/list`).then(
    (res) => res.json(),
  );
  const target = targets.find(
    ({ type, url }) => type === "page" && url === "about:blank",
  );
  assert.ok(target?.webSocketDebuggerUrl, "Edge should have an isolated page");
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await once(socket, "open", { signal: AbortSignal.timeout(10_000) });
  let nextId = 0;
  const requests = new Map();
  socket.on("message", (data) => {
    const { id, error, result } = JSON.parse(data);
    requests.get(id)?.(error, result);
  });
  function call(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++nextId;
      const timer = setTimeout(() => {
        requests.delete(id);
        reject(new Error(`Edge did not answer ${method}`));
      }, 12_000);
      requests.set(id, (error, result) => {
        clearTimeout(timer);
        requests.delete(id);
        if (error) reject(new Error(error.message));
        else resolve(result);
      });
      socket.send(JSON.stringify({ id, method, params }));
    });
  }
  async function evaluate(expression) {
    const result = await call("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    assert.equal(
      result.exceptionDetails,
      undefined,
      result.exceptionDetails?.exception?.description,
    );
    return result.result.value;
  }
  return { call, evaluate };
}

test(
  "administrator edits a persisted playlist and drops stale previews on reconnect",
  {
    skip: !base || !api ? "Set the two private camera lab fixture URLs" : false,
    timeout: 100_000,
  },
  async (t) => {
    for (const address of [base, api]) {
      assert.match(new URL(address).hostname, /^(127\.0\.0\.1|localhost)$/);
    }
    const control = async (body = {}) => {
      const response = await fetch(`${api}/__fixture`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      assert.equal(response.status, 200);
      const state = await response.json();
      assert.ok(Array.isArray(state.ids), "Fixture API must be available");
      return state;
    };
    await control({ reset: true });
    const session = await fetch(`${base}/api/v1/auth/session/`).then((res) =>
      res.json(),
    );
    assert.equal(
      session.csrf_token,
      "TEST_ONLY_CSRF",
      "Frontend must be wired to the fixture",
    );

    const { call, evaluate } = await openBrowser(t);
    const wait = async (expression, label) => {
      try {
        await waitFor(() => evaluate(expression), label);
      } catch (error) {
        const page = await evaluate(
          "({ path: location.pathname, text: document.body?.innerText.slice(0, 500) })",
        );
        throw new Error(`${label}: ${JSON.stringify(page)}`, { cause: error });
      }
    };
    const go = async (pathname) => {
      const { errorText } = await call("Page.navigate", {
        url: `${base}${pathname}`,
      });
      assert.equal(errorText, undefined);
    };
    const button = (
      label,
    ) => `[...document.querySelectorAll('button')].find(button =>
    (button.getAttribute('aria-label') || button.textContent.trim()) === ${JSON.stringify(label)})`;
    const click = async (label) => {
      await wait(
        `Boolean(${button(label)}) && !(${button(label)}).disabled`,
        label,
      );
      await evaluate(`(${button(label)}).click()`);
    };
    const jpeg = (width) =>
      evaluate(`(() => {
    const canvas = document.createElement('canvas');
    canvas.width = ${width}; canvas.height = 72;
    return canvas.toDataURL('image/jpeg');
  })()`);
    const cameras = '[aria-labelledby="lab-control-cameras"]';
    const frameWidth = `document.querySelector(${JSON.stringify(`${cameras} img`)})?.naturalWidth`;
    const sourceTitle =
      "Sensor-based Pallet Activity Recognition in Logistics (SPARL Version 2)";
    const dockA =
      "Ensayo de carga y descarga de un palé de la estantería mediante un apilador.";
    const dockB =
      "Ensayo de preparación y entrega de un palé a una cinta transportadora.";

    await control({
      managedCamera: await jpeg(128),
      labCatalog: [
        {
          id: "media-a",
          filename: "SPARL-S3-Record3-Camera1.mp4",
          title: sourceTitle,
          scenario: dockA,
          duration_s: 120,
        },
        {
          id: "media-b",
          filename: "SPARL-S1-Record1-Camera2.mp4",
          title: sourceTitle,
          scenario: dockB,
          duration_s: 467,
        },
        {
          id: "media-c",
          filename: "fallback.mp4",
          title: sourceTitle,
          scenario: " ",
        },
      ],
    });
    const login = await fetch(`${api}/api/v1/auth/login/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": session.csrf_token,
      },
      body: JSON.stringify({
        username: "fixture-admin",
        password: "TEST_ONLY_PASSWORD",
      }),
    });
    assert.equal(login.status, 200);
    await call("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await go(route);
    await wait(`${frameWidth} === 128`, "initial camera preview");

    const form =
      "document.querySelector('form[aria-label^=\"Lista de reproducción\"]')";
    assert.deepEqual(
      await evaluate(
        `[...${form}.querySelectorAll('select option')].slice(1).map(option => option.textContent)`,
      ),
      [dockA, dockB, "fallback.mp4"],
    );
    const add = async (id) => {
      await evaluate(`(() => {
      const select = ${form}.querySelector('select');
      select.value = ${JSON.stringify(id)};
      select.dispatchEvent(new Event('change', { bubbles: true }));
    })()`);
      await click("Añadir");
    };
    await add("media-a");
    await add("media-b");
    await click(`Subir ${dockB} (posición 2)`);
    await evaluate(`${form}.querySelector('[role=switch]').click()`);
    await click("Guardar lista");
    await wait(
      `${form}.textContent.includes('Cambios guardados.')`,
      "save confirmation",
    );

    const persisted = await fetch(`${api}${controlPath}`).then((res) =>
      res.json(),
    );
    assert.deepEqual(persisted.playlists[cameraId], {
      media_ids: ["media-b", "media-a"],
      repeat: true,
    });
    const navigation = await evaluate("performance.timeOrigin");
    await call("Page.reload", { ignoreCache: true });
    await wait(
      `performance.timeOrigin !== ${navigation} && Boolean(${form}) && ${frameWidth} === 128`,
      "refetched playlist and preview",
    );
    assert.deepEqual(
      await evaluate(
        `[...${form}.querySelectorAll('ol li')].map(row => row.querySelector('p').textContent)`,
      ),
      [dockB, dockA],
    );
    assert.equal(
      await evaluate(`${form}.querySelector('ol li p + p').textContent`),
      "SPARL-S1-Record1-Camera2.mp4 · 467 s",
    );
    assert.equal(
      await evaluate("document.documentElement.scrollWidth <= innerWidth"),
      true,
    );
    assert.equal(
      await evaluate(`${form}.querySelector('[role=switch]').checked`),
      true,
    );

    await control({ holdLabPreview: true });
    await waitFor(
      async () => (await control()).labPreviewWaiting,
      "an old JPEG request in flight",
    );
    await control({ labCameraStatus: "reconnecting" });
    await wait(
      `document.querySelector(${JSON.stringify(cameras)}).textContent.includes('Sin fotograma reciente')`,
      "reconnect snapshot",
    );
    assert.equal(await evaluate(`typeof (${frameWidth})`), "undefined");
    await evaluate(`(() => {
      window.labLoadedWidths = [];
      document.addEventListener('load', ({ target }) => {
        if (target instanceof HTMLImageElement && target.closest(${JSON.stringify(cameras)}))
          window.labLoadedWidths.push(target.naturalWidth);
      }, true);
    })()`);
    await control({ releaseLabPreview: true });
    assert.equal(await evaluate(`typeof (${frameWidth})`), "undefined");
    await control({
      labCameraStatus: "analyzing",
      labPreview: await jpeg(192),
    });
    await wait(
      `${frameWidth} === 192 && window.labLoadedWidths.includes(192)`,
      "fresh JPEG after reconnect",
    );
    assert.deepEqual(await evaluate("window.labLoadedWidths"), [192]);
  },
);

test(
  "temporary auth and transport failures keep the lab mounted until confirmed expiration",
  {
    skip: !base || !api ? "Set the two private camera lab fixture URLs" : false,
    timeout: 100_000,
  },
  async (t) => {
    for (const address of [base, api]) {
      assert.match(new URL(address).hostname, /^(127\.0\.0\.1|localhost)$/);
    }
    const post = async (path, body, headers) => {
      const response = await fetch(`${api}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify(body),
      });
      assert.equal(response.status, 200);
    };
    await post("/__fixture", {
      reset: true,
      managedCamera: "data:image/jpeg;base64,/9j/2Q==",
    });
    const sessionPath = "/api/v1/auth/session/";
    const { csrf_token: csrfToken } = await fetch(`${base}${sessionPath}`).then(
      (response) => response.json(),
    );
    assert.equal(csrfToken, "TEST_ONLY_CSRF");
    await post(
      "/api/v1/auth/login/",
      { username: "fixture-admin", password: "TEST_ONLY_PASSWORD" },
      { "X-CSRFToken": csrfToken },
    );
    const { call, evaluate } = await openBrowser(t);
    await call("Page.navigate", { url: `${base}${route}` });
    const wait = (expression, label) =>
      waitFor(() => evaluate(expression), label);
    const toggle = (label) =>
      `[...document.querySelectorAll('button')].find(button =>
        button.textContent.trim() === "${label}" && !button.disabled)`;
    const disable = toggle("Deshabilitar laboratorio");
    const enable = toggle("Habilitar laboratorio");
    await wait(`Boolean(${disable})`, "lab loaded with an active session");
    await evaluate(`(${disable}).click()`);
    await wait(`Boolean(${enable})`, "lab ready for activation");
    await evaluate(`(() => {
      const originalFetch = window.fetch;
      window.labHeading = document.querySelector("h1");
      window.sessionFailures = 0;
      window.activationAttempts = 0;
      window.fetch = (url, init) => {
        if (url === "${sessionPath}" && window.sessionFailures < 2) {
          window.sessionFailures++;
          return Promise.resolve(new Response("Unavailable", { status: 503 }));
        }
        if (url === "${controlPath}" && init?.method === "PATCH" && ++window.activationAttempts === 1) {
          return Promise.resolve(new Response(null, { status: 401 }));
        }
        return originalFetch(url, init);
      };
      window.dispatchEvent(new Event("focus"));
    })()`);
    await wait("window.sessionFailures === 1", "transient focus failure");
    await evaluate(`(${enable})?.click()`);
    await wait(
      `document.body.innerText.includes("No se pudo completar la consulta con Operix.") && Boolean(${enable})`,
      "failed PATCH recovers on the next lab poll",
    );
    assert.equal(await evaluate("window.sessionFailures"), 2);
    assert.equal(await evaluate("window.activationAttempts"), 1);
    assert.equal(
      await evaluate(
        `location.pathname === "${route}" && document.querySelector("h1") === window.labHeading`,
      ),
      true,
    );
    await evaluate(`(${enable}).click()`);
    await wait(`Boolean(${disable})`, "explicit retry succeeded");
    await post("/__fixture", { expire: true });
    await wait(
      `location.pathname === "/login" &&
        new URLSearchParams(location.search).get("next") === "${route}" &&
        document.body.innerText.includes("Tu sesión terminó.")`,
      "confirmed expiration returns to login with the lab as the destination",
    );
  },
);
