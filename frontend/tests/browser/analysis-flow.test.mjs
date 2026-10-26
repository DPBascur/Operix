// Chromium mediante CDP nativo de Node: sin framework ni dependencias nuevas.
import assert from "node:assert/strict";
import test from "node:test";
import { spawn } from "node:child_process";
import { access, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { eventId } from "../fixtures/analysis-api.mjs";

// Transporte WS ya distribuido con Next fijado; no instala otro paquete.
const { WebSocket } = createRequire(import.meta.url)("next/dist/compiled/ws");

const base = process.env.OPERIX_BROWSER_BASE_URL ?? "http://127.0.0.1:3000";
const api = process.env.OPERIX_FIXTURE_URL ?? "http://127.0.0.1:8000";
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test(
  "flujo web: sesión, progreso, navegación, evidencia, teclado y estados terminales",
  { timeout: 120000 },
  async () => {
    // Nunca ejecutar las acciones de este test contra una API real.
    const control = async (body = {}) => {
      const response = await fetch(`${api}/__fixture`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      assert.equal(
        response.status,
        200,
        "Se requiere la API fixture explícita",
      );
      const value = await response.json();
      assert.ok(Array.isArray(value.ids));
      return value;
    };
    await control({ reset: true });
    let executable = process.env.OPERIX_BROWSER_EXECUTABLE;
    for (const candidate of executable
      ? [executable]
      : [
          "C:/Program Files/Google/Chrome/Application/chrome.exe",
          "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
          "/usr/bin/chromium",
          "/usr/bin/google-chrome",
        ]) {
      try {
        await access(candidate);
        executable = candidate;
        break;
      } catch {
        /* Otro navegador instalado. */
      }
    }
    assert.ok(
      executable,
      "Indique OPERIX_BROWSER_EXECUTABLE para un Chromium instalado",
    );
    const root = await mkdtemp(path.join(tmpdir(), "operix-browser-"));
    const child = spawn(
      executable,
      [
        "--headless=new",
        "--remote-debugging-port=0",
        `--user-data-dir=${path.join(root, "profile")}`,
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
      ],
      { windowsHide: true, stdio: ["ignore", "ignore", "pipe"] },
    );
    let socket;
    try {
      const endpoint = await new Promise((resolve, reject) => {
        let output = "";
        const timeout = setTimeout(
          () => reject(new Error("Chromium no abrió CDP")),
          15000,
        );
        child.once("error", reject);
        child.stderr.on("data", (chunk) => {
          output += chunk;
          const match = output.match(/DevTools listening on (ws:\/\/[^\s]+)/);
          if (match) {
            clearTimeout(timeout);
            resolve(match[1]);
          }
        });
      });
      const port = new URL(endpoint).port;
      const target = await (
        await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, {
          method: "PUT",
        })
      ).json();
      socket = new WebSocket(endpoint);
      await new Promise((resolve, reject) => {
        socket.addEventListener("open", resolve, { once: true });
        socket.addEventListener("error", reject, { once: true });
      });
      let next = 0;
      let sessionId;
      const pending = new Map();
      socket.addEventListener("message", ({ data }) => {
        const response = JSON.parse(data);
        if (response.id && pending.has(response.id)) {
          const { resolve, reject, timeout } = pending.get(response.id);
          pending.delete(response.id);
          clearTimeout(timeout);
          if (response.error) reject(new Error(response.error.message));
          else resolve(response.result);
        }
      });
      const call = (method, params = {}) =>
        new Promise((resolve, reject) => {
          const id = ++next;
          const timeout = setTimeout(() => {
            pending.delete(id);
            reject(new Error(`CDP timeout: ${method}`));
          }, 15000);
          pending.set(id, { resolve, reject, timeout });
          socket.send(
            JSON.stringify({
              id,
              method,
              params,
              ...(sessionId ? { sessionId } : {}),
            }),
          );
        });
      const evaluate = async (expression) => {
        const response = await call("Runtime.evaluate", {
          expression,
          returnByValue: true,
          awaitPromise: true,
        });
        assert.equal(
          response.exceptionDetails,
          undefined,
          JSON.stringify(response.exceptionDetails),
        );
        return response.result.value;
      };
      const wait = async (expression) => {
        const deadline = Date.now() + 25000;
        while (Date.now() < deadline) {
          if (await evaluate(expression)) return;
          await pause(100);
        }
        throw new Error(
          `No se cumplió: ${expression}\n${await evaluate("document.body.innerText")}`,
        );
      };
      const text = (value) =>
        `document.body.innerText.includes(${JSON.stringify(value)})`;
      const click = async (name) => {
        const expression = `[...document.querySelectorAll('button')].find(b=>b.offsetParent!==null && b.innerText.trim().replace(/\\s+/g,' ')===${JSON.stringify(name)} && !b.disabled)`;
        await wait(`!!(${expression})`);
        await evaluate(`(${expression}).click()`);
      };
      const go = async (route) => {
        await call("Page.navigate", { url: `${base}${route}` });
        await wait(
          "document.readyState==='complete' && !!document.querySelector('main')",
        );
      };
      const navigate = async (href) => {
        await evaluate(
          `document.querySelector('nav a[href=${JSON.stringify(href)}]').click()`,
        );
        await wait(`location.pathname===${JSON.stringify(href)}`);
      };
      const viewport = (width) =>
        call("Emulation.setDeviceMetricsOverride", {
          width,
          height: 900,
          deviceScaleFactor: 1,
          mobile: false,
        });
      sessionId = (
        await call("Target.attachToTarget", {
          targetId: target.id,
          flatten: true,
        })
      ).sessionId;
      await viewport(1440);
      await go("/analysis?source=manual");
      await click("Perfil B Demo B");
      await wait(text("TEST_DATA_B.mp4"));
      await click("Iniciar análisis");
      await wait(text("Preparando modelos y video"));
      assert.equal(
        await evaluate("!!document.querySelector('.analysis-state.is-error')"),
        false,
        "Preparación no es error",
      );
      await wait(text("99.9 %"));
      const before = await control();
      await navigate("/events");
      await wait(text("Proximidad persona"));
      assert.equal(
        (await control()).deleted,
        before.deleted,
        "Navegar no borra sesión",
      );
      await navigate("/analysis");
      await wait(text("Análisis completado"));
      assert.equal(
        (await control()).created,
        before.created,
        "Recupera sesión, sin POST nuevo",
      );
      await wait(
        "!!document.querySelector('video[aria-label=\"Resultado anotado de Operix\"]')",
      );
      await wait("document.querySelector('video').readyState>=1");
      await evaluate(
        "(async()=>{const video=document.querySelector('video');video.muted=true;await video.play();})()",
      );
      await wait("!document.querySelector('video').paused");
      await evaluate("document.querySelector('video').pause()");
      assert.equal(
        await evaluate("document.querySelector('video').paused"),
        true,
      );
      await evaluate("document.querySelector('video').currentTime=2");
      await wait("Math.abs(document.querySelector('video').currentTime-2)<.1");
      await evaluate("document.querySelector('video').currentTime=0");
      await wait("document.querySelector('video').currentTime<.1");
      await click("Editar zona");
      await click("Nueva zona");
      const input = async (label, value) => {
        await evaluate(
          `(()=>{const input=[...document.querySelectorAll('label')].find(l=>l.textContent.trim().startsWith(${JSON.stringify(label)})).querySelector('input'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,${JSON.stringify(value)}); input.dispatchEvent(new Event('input',{bubbles:true}));})()`,
        );
      };
      for (const [x, y] of [
        [10, 10],
        [90, 10],
        [90, 90],
        [10, 90],
      ]) {
        await input("X (%)", String(x));
        await input("Y (%)", String(y));
        await click("Añadir vértice");
      }
      await click("Cerrar polígono");
      await click("Aplicar zona");
      await wait(text("Hay cambios de zona pendientes"));
      await control({ delayNextZone: true });
      await click("Editar zona");
      await click("Aplicar zona");
      const zoneDeadline = Date.now() + 5000;
      while (!(await control()).waitingZones && Date.now() < zoneDeadline)
        await pause(50);
      assert.equal((await control()).waitingZones, 1);
      await navigate("/events");
      await wait(text("Proximidad persona"));
      await navigate("/analysis");
      await wait(text("Hay cambios de zona pendientes"));
      await control({ releaseZones: true });
      await pause(200);
      assert.equal((await control()).waitingZones, 0);
      assert.equal(
        await evaluate(text("Hay cambios de zona pendientes")),
        true,
      );
      assert.equal(await evaluate(text("No se pudo aplicar la zona.")), false);
      await control({ failNext: true });
      await click("Volver a analizar");
      await wait(text("Error de análisis"));
      assert.equal(
        await evaluate(
          "!!document.querySelector('video[aria-label=\"Resultado anotado de Operix\"]')",
        ),
        false,
      );
      await click("Volver a intentar");
      await wait(text("Preparando modelos"));
      await control({ delayNextStatus: true });
      const delayDeadline = Date.now() + 5000;
      while (!(await control()).waitingStatus && Date.now() < delayDeadline)
        await pause(50);
      assert.equal((await control()).waitingStatus, true);
      await click("Detener");
      await wait(text("Análisis detenido"));
      await pause(1200);
      assert.equal(
        await evaluate(text("Análisis detenido")),
        true,
        "Un poll anterior no sustituye la cancelación",
      );
      await navigate("/events");
      await wait(text("Proximidad persona"));
      await wait(`!!document.querySelector('a[href="/events/${eventId}"]')`);
      await evaluate(
        `document.querySelector('a[href="/events/${eventId}"]').click()`,
      );
      await wait(text("Resumen operacional"));
      await wait(
        "!!document.querySelector('figure img') && document.querySelector('figure img').complete && document.querySelector('figure img').naturalWidth>0",
      );
      assert.equal(
        await evaluate(
          text("requiere revisión humana, no confirma un incidente"),
        ),
        true,
      );
      for (const width of [1440, 1280, 390]) {
        await viewport(width);
        for (const route of [
          "/",
          "/events",
          `/events/${eventId}`,
          "/indicators",
          "/zones",
          "/analysis",
        ]) {
          await go(route);
          await wait("document.fonts.status==='loaded'");
          assert.equal(
            await evaluate(
              "document.documentElement.scrollWidth<=innerWidth+1",
            ),
            true,
            `Overflow: ${width} ${route}`,
          );
        }
      }
      const screenshot = await call("Page.captureScreenshot", {
        format: "png",
      });
      await writeFile(
        path.join(root, "analysis-mobile.png"),
        Buffer.from(screenshot.data, "base64"),
      );
      // El artefacto es desechable y nunca entra a Git.
      assert.ok(
        (await readFile(path.join(root, "analysis-mobile.png"))).length > 100,
      );
      console.log(
        "PASS: navegación sin DELETE, recuperación, 99.9 antes de completed, MP4/seek, polígono por teclado, error/cancelación, histórico/evidencia, 18 combinaciones de viewport/ruta.",
      );
    } finally {
      socket?.close();
      child.kill();
      await new Promise((resolve) => {
        if (child.exitCode !== null) resolve();
        else {
          child.once("exit", resolve);
          setTimeout(resolve, 3000).unref();
        }
      });
      const resolved = path.resolve(root);
      assert.ok(
        resolved.startsWith(path.resolve(tmpdir()) + path.sep) &&
          path.basename(resolved).startsWith("operix-browser-"),
      );
      await rm(resolved, {
        recursive: true,
        force: true,
        maxRetries: 4,
        retryDelay: 500,
      });
    }
  },
);
