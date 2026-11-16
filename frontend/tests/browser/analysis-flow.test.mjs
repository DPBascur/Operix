// Chromium mediante CDP nativo de Node: sin framework ni dependencias nuevas.
import assert from "node:assert/strict";
import test from "node:test";
import { spawn } from "node:child_process";
import { access, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { eventId } from "../fixtures/analysis-api.mjs";
import { checkButtonThemes } from "./theme-geometry.mjs";

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
      let resolveLoad;
      let discardConfirmation;
      const pending = new Map();
      socket.addEventListener("message", ({ data }) => {
        const response = JSON.parse(data);
        if (
          response.sessionId === sessionId &&
          response.method === "Page.loadEventFired"
        ) {
          resolveLoad?.();
        }
        if (
          response.sessionId === sessionId &&
          response.method === "Page.javascriptDialogOpening"
        ) {
          discardConfirmation?.(response.params);
        }
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
            reject(
              new Error(
                `CDP timeout: ${method} ${params.expression?.slice(0, 120) ?? ""}`,
              ),
            );
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
        const loaded = new Promise((resolve) => {
          resolveLoad = resolve;
        });
        const timer = setTimeout(() => resolveLoad?.(), 10000);
        try {
          const navigation = await call("Page.navigate", {
            url: `${base}${route}`,
          });
          assert.equal(navigation.errorText, undefined);
          await loaded;
        } finally {
          clearTimeout(timer);
          resolveLoad = undefined;
        }
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
      await call("Page.enable");
      await viewport(1440);
      await go("/rules");
      await wait("location.pathname==='/login'");
      const credentials = async (password) => {
        await evaluate(`(() => {
          document.querySelector('#login-username').value = 'fixture-admin';
          document.querySelector('#login-password').value = ${JSON.stringify(password)};
        })()`);
        await click("Ingresar");
      };
      await credentials("invalid");
      await wait(text("Usuario o contraseña incorrectos."));
      await credentials("TEST_ONLY_PASSWORD");
      await wait(text("Reglas por perfil"));
      await wait(text("Proximidad persona ↔ montacargas · v2 · Habilitada"));
      await evaluate(
        "[...document.querySelectorAll('main summary')].find(el=>el.textContent.includes('Habilitada')).parentElement.open=true",
      );
      await wait(text("Distancia máxima configurada"));
      const accountTrigger = "[...document.querySelectorAll('button[aria-label^=\"Opciones de cuenta\"]')].find(b=>b.offsetParent!==null)";
      await wait(`!!(${accountTrigger})`);
      await evaluate(`(${accountTrigger}).focus()`);
      await call("Input.dispatchKeyEvent", { type: "keyDown", key: "Enter", code: "Enter", text: "\r", windowsVirtualKeyCode: 13 });
      await call("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
      await wait(`(${accountTrigger}).getAttribute('aria-expanded')==='true'`);
      await call("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
      await wait(`(${accountTrigger}).getAttribute('aria-expanded')==='false' && document.activeElement===(${accountTrigger})`);
      await evaluate(`(${accountTrigger}).click()`);
      await evaluate("document.querySelector('.app-sidebar a[href=\"/account\"]').click()");
      await wait("location.pathname==='/account'");
      await wait(`(${accountTrigger})?.getAttribute('aria-expanded')==='false'`);
      await wait(text("Mi cuenta"));
      await click("Mostrar contraseñas");
      await wait("document.querySelector('#current')?.type === 'text'");
      await evaluate(`(() => {
        document.querySelector('#current').value = 'TEST_ONLY_PASSWORD';
        document.querySelector('#next').value = 'TEST_ONLY_LONG_PASSWORD';
        document.querySelector('#confirmation').value = 'TEST_ONLY_LONG_PASSWORD';
      })()`);
      await click("Cambiar contraseña");
      await wait(text("Contraseña actualizada."));
      await go("/users");
      await wait(text("Admin de prueba"));
      await click("Nueva cuenta");
      await evaluate(`(() => {
        document.querySelector('#directory-username').value = 'fixture-viewer';
        document.querySelector('#directory-display-name').value = 'Cuenta de visualización';
        document.querySelector('#directory-password').value = 'TEST_ONLY_DIRECTORY_PASSWORD';
      })()`);
      await click("Crear cuenta");
      await wait(text("Cuenta creada."));
      await click("Editar");
      await evaluate("document.querySelector('#directory-role').value='safety_lead'");
      await click("Guardar cambios");
      await wait(text("Cambios guardados."));
      await wait("document.querySelector('#directory-role').value==='safety_lead'");
      await evaluate("document.querySelector('#directory-role').value='viewer'");
      await click("Guardar cambios");
      await wait("document.querySelector('#directory-role').value==='viewer'");
      await click("Restablecer contraseña");
      await evaluate("document.querySelector('#directory-password').value='TEST_ONLY_RESET_PASSWORD'");
      await click("Restablecer");
      await wait(text("Contraseña restablecida."));
      await go("/analysis?source=manual");
      await click("Perfil B Demo B");
      await wait(text("TEST_DATA_B.mp4"));
      await click("Detalles");
      await wait(text("REGLAS DEL PRÓXIMO ANÁLISIS"));
      await click("Detalles");
      await click("Zonas, calibración y reglas");
      await wait(text("Configuración preparada de esta fuente"));
      await wait(text("En sesi\u00f3n: configuraci\u00f3n inicial"));
      assert.equal(
        await evaluate(
          "[...document.querySelectorAll('button')].find(b=>b.innerText.includes('Iniciar análisis'))?.disabled",
        ),
        true,
      );
      await wait(
        "document.querySelector('[aria-label=\"Zona seleccionada\"]') !== null",
      );
      await click("Guardar configuración");
      await wait(text("Configuración guardada para el próximo análisis."));
      await wait(text("En sesi\u00f3n: revisi\u00f3n 1"));
      await click("Calibrar / recalibrar");
      await wait(
        text(
          "Confirmo cámara fija, referencias medidas y zonas revisadas para este encuadre",
        ),
      );
      await wait(
        "document.querySelector('video[aria-label=\"Referencia de configuración\"]')?.readyState >= 2",
      );
      await click("Capturar primer fotograma");
      await wait(
        "!!document.querySelector('img[alt=\"Fotograma de la fuente para configuración espacial\"]')",
      );
      await evaluate(
        "document.querySelector('img[alt=\"Fotograma de la fuente para configuración espacial\"]').decode()",
      );
      assert.equal(
        await evaluate(
          `(() => {const img=document.querySelector('img[alt="Fotograma de la fuente para configuración espacial"]');const c=document.createElement('canvas');c.width=16;c.height=16;const ctx=c.getContext('2d');ctx.drawImage(img,0,0,16,16);return ctx.getImageData(0,0,16,16).data.some((v,i)=>i%4===3 && v>0);})()`,
        ),
        true,
        "La referencia capturada debe contener imagen, no transparencia",
      );
      await evaluate(
        `(() => {const select=[...document.querySelectorAll('select')].find(s=>[...s.options].some(o=>o.value==='calibration'));select.value='calibration';select.dispatchEvent(new Event('change',{bubbles:true}));})()`,
      );
      for (const [x, y] of [
        [0.1, 0.1],
        [0.9, 0.1],
        [0.9, 0.9],
        [0.1, 0.9],
      ]) {
        await evaluate(
          `(() => {const svg=document.querySelector('svg[aria-label="Editor de puntos"]');const r=svg.getBoundingClientRect();svg.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,clientX:r.left+r.width*${x},clientY:r.top+r.height*${y}}));})()`,
        );
      }
      await wait(text("Referencia 4"));
      const previousTheme = await evaluate(
        "document.documentElement.dataset.theme",
      );
      await evaluate("document.documentElement.dataset.theme='light'");
      await viewport(390);
      assert.equal(
        await evaluate("document.documentElement.scrollWidth <= innerWidth"),
        true,
      );
      for (const width of [390, 1440]) {
        await viewport(width);
        await evaluate(
          "document.querySelector('[aria-label=\"Configuración espacial\"]').scrollIntoView({block:'start'})",
        );
        if (process.env.OPERIX_BROWSER_ARTIFACT_DIR) {
          const shot = await call("Page.captureScreenshot", { format: "png" });
          await writeFile(
            path.join(
              process.env.OPERIX_BROWSER_ARTIFACT_DIR,
              `spatial-editor-${width}.png`,
            ),
            Buffer.from(shot.data, "base64"),
          );
        }
      }
      await evaluate(
        `document.documentElement.dataset.theme=${JSON.stringify(previousTheme)}`,
      );
      const discard = new Promise((resolve) => {
        discardConfirmation = resolve;
      });
      const cancelEdit = click("Cancelar edición");
      const confirmation = await Promise.race([discard, cancelEdit.then(() => null)]);
      if (confirmation) {
        assert.equal(confirmation.type, "confirm");
        assert.equal(confirmation.message, "¿Descartar los cambios espaciales sin guardar?");
        await call("Page.handleJavaScriptDialog", { accept: true });
      }
      await cancelEdit;
      discardConfirmation = undefined;
      // Demo → archivo propio: la API entrega una zona vacía, sin polígonos ocultos.
      await evaluate(
        `(async()=>{const video=document.querySelector('video'); const blob=await (await fetch(video.src)).blob(); const dt=new DataTransfer();dt.items.add(new File([blob], 'TEST_DATA_custom.mp4', {type:'video/mp4'}));const input=document.querySelector('input[type=file]');input.files=dt.files;input.dispatchEvent(new Event('change',{bubbles:true}));})()`,
      );
      await wait(text("Crear zona"));
      assert.equal(
        await evaluate("document.querySelectorAll('polygon').length"),
        0,
      );
      await click("Crear zona");
      await evaluate(
        `(()=>{const svg=document.querySelector('svg[viewBox="0 0 100 100"]');const r=svg.getBoundingClientRect();for(const [x,y] of [[.1,.1],[.9,.1],[.9,.9],[.1,.9]])svg.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,clientX:r.left+x*r.width,clientY:r.top+y*r.height}));})()`,
      );
      await wait("document.querySelectorAll('ellipse').length===4");
      await click("Cerrar polígono");
      await click("Aplicar zona");
      await wait(text("Editar zona"));
      // Otro archivo propio vuelve a empezar vacío; el anterior no se reutiliza.
      await evaluate(
        `(async()=>{const blob=await (await fetch(document.querySelector('video').src)).blob();const dt=new DataTransfer();dt.items.add(new File([blob],'TEST_DATA_other.mp4',{type:'video/mp4'}));const input=document.querySelector('input[type=file]');input.files=dt.files;input.dispatchEvent(new Event('change',{bubbles:true}));})()`,
      );
      await wait(text("Crear zona"));
      assert.equal(
        await evaluate("document.querySelectorAll('polygon').length"),
        0,
      );
      await click("Perfil A Demo A");
      await wait(text("Crear zona"));
      // En una fuente manual cambiar perfil tampoco importa la geometría demo.
      assert.equal(
        await evaluate("document.querySelectorAll('polygon').length"),
        0,
      );
      await evaluate(
        "document.querySelector('details.analysis-more').open=true",
      );
      await click("Limpiar sesión");
      await wait(text("Sin fuente preparada"));
      await go("/analysis?profile=B");
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
      await wait(text("Vista previa muestreada."));
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
      await click("Detalles");
      await wait(text("REGLAS DEL RESULTADO"));
      await click("Detalles");
      assert.equal(
        (await control()).created,
        before.created,
        "Recupera sesión, sin POST nuevo",
      );
      await wait(
        "!!document.querySelector('video[aria-label=\"Resultado anotado de Operix\"]')",
      );
      await wait("document.querySelector('video').readyState>=1");
      await wait(text("MP4 listo para reproducir"));
      const sidebarSize = "document.querySelector('#operix-sidebar').getBoundingClientRect().width";
      const expandedWidth = await evaluate(sidebarSize);
      const sizingSession = await control();
      await evaluate("void (window.sidebarVideo = document.querySelector('.analysis-stage video'))");
      await evaluate("document.querySelector('button[aria-label=\"Contraer barra lateral\"]').click()");
      await wait(`${sidebarSize} < 80`);
      await wait("localStorage.getItem('operix-sidebar')==='compact'");
      assert.ok(expandedWidth > 200);
      assert.equal(await evaluate("window.sidebarVideo === document.querySelector('.analysis-stage video')"), true);
      assert.equal((await control()).created, sizingSession.created);
      assert.equal((await control()).deleted, sizingSession.deleted);
      await evaluate("document.querySelector('#operix-sidebar a[href=\"/analysis\"]').focus()");
      await wait("document.querySelector('[role=tooltip]')?.textContent==='Análisis'");
      await wait("document.querySelector('#operix-sidebar a[aria-current=page]')?.pathname==='/analysis'");
      await evaluate(`(${accountTrigger}).click()`);
      await wait("!!document.querySelector('#operix-sidebar a[href=\"/account#account-security\"]')");
      await evaluate("document.querySelector('main').dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}))");
      await wait(`(${accountTrigger}).getAttribute('aria-expanded')==='false'`);
      await evaluate("document.querySelector('button[aria-label=\"Expandir barra lateral\"]').click()");
      await wait(`${sidebarSize} > 200`);
      assert.equal(await evaluate("window.sidebarVideo === document.querySelector('.analysis-stage video')"), true);
      assert.equal(
        await evaluate("document.querySelector('video').playbackRate"),
        1,
      );
      assert.ok(
        await evaluate(
          "Math.abs(document.querySelector('video').duration-277/30)<.05",
        ),
      );
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
        [10, 50],
      ]) {
        await input("X (%)", String(x));
        await input("Y (%)", String(y));
        await click("Añadir vértice");
      }
      await click("Cerrar polígono");
      await evaluate("document.querySelectorAll('ellipse')[4].focus()");
      await click("Eliminar vértice");
      await wait("document.querySelectorAll('ellipse').length===4");
      await evaluate("document.querySelectorAll('ellipse')[3].focus()");
      await call("Input.dispatchKeyEvent", {
        type: "keyDown",
        key: "Delete",
        code: "Delete",
        windowsVirtualKeyCode: 46,
      });
      await wait("document.querySelectorAll('ellipse').length===3");
      await evaluate("document.querySelector('ellipse').focus()");
      assert.equal(
        await evaluate(
          "[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Eliminar vértice').disabled",
        ),
        true,
      );
      await call("Input.dispatchKeyEvent", {
        type: "keyDown",
        key: "Backspace",
        code: "Backspace",
        windowsVirtualKeyCode: 8,
      });
      assert.equal(
        await evaluate("document.querySelectorAll('ellipse').length"),
        3,
      );
      await click("Aplicar zona");
      await wait(text("Hay cambios de configuración pendientes"));
      const currentIds = (await control()).ids;
      const applied = await (
        await fetch(
          `${api}/api/v1/analysis/sessions/${currentIds.at(-1)}/status/`,
        )
      ).json();
      assert.equal(
        applied.zone.polygon.length,
        3,
        "La zona guardada coincide con los tres puntos visibles",
      );
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
      await wait(text("Hay cambios de configuración pendientes"));
      await control({ releaseZones: true });
      await pause(200);
      assert.equal((await control()).waitingZones, 0);
      assert.equal(
        await evaluate(text("Hay cambios de configuración pendientes")),
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
      await wait("document.querySelector('[role=tab][aria-selected=true]')?.innerText === 'Fotograma'");
      assert.equal(
        await evaluate("!!document.querySelector('figure video')"),
        false,
        "El expediente difiere la carga del clip hasta que se selecciona",
      );
      await click("Clip");
      await wait(
        "document.querySelector('video[aria-label=\"Clip anotado del evento\"]')?.readyState >= 1",
      );
      await evaluate(
        "(async()=>{const video=document.querySelector('video[aria-label=\"Clip anotado del evento\"]');video.muted=true;await video.play();})()",
      );
      await wait(
        "document.querySelector('video[aria-label=\"Clip anotado del evento\"]').currentTime > 0",
      );
      await evaluate(
        "document.querySelector('video[aria-label=\"Clip anotado del evento\"]').pause()",
      );
      await evaluate("document.querySelector('figure video').currentTime = 0.1");
      await wait("document.querySelector('figure video').currentTime >= 0.09");
      await wait("!!document.querySelector('figure meter')");
      await click("Fotograma");
      await wait("!document.querySelector('figure video')");
      for (const value of [
        "Persona",
        "Montacargas",
        "Distancia normalizada",
        "0,1",
        "Máximo configurado",
        "0,25",
        "Duración de la condición",
        "Mínimo configurado",
      ])
        await wait(text(value));
      const subjects = await evaluate(
        "Object.fromEntries([...document.querySelectorAll('main dt')].filter(dt=>['Persona','Montacargas'].includes(dt.innerText)).map(dt=>[dt.innerText,dt.nextElementSibling.innerText]))",
      );
      assert.deepEqual(subjects, {
        Persona: "ID de seguimiento 1",
        Montacargas: "ID de seguimiento 1",
      });
      await evaluate(
        "[...document.querySelectorAll('summary')].find(s=>s.innerText.includes('Trazabilidad técnica')).click()",
      );
      await wait(text("person_equipment_nearest_ground_edges_v1"));
      await wait(text("[0.2,0.5]"));
      await wait(text("[0.3,0.5]"));
      await wait(
        "!!document.querySelector('figure img') && document.querySelector('figure img').complete && document.querySelector('figure img').naturalWidth>0",
      );
      assert.equal(
        await evaluate(
          text("requiere revisión humana, no confirma un incidente"),
        ),
        true,
      );
      await go("/indicators");
      await wait(text("Eventos por procedencia"));
      assert.equal(await evaluate(text("Ejemplo ilustrativo")), false);
      const setProvenance = (value) =>
        evaluate(`(() => {
        const select = [...document.querySelectorAll('main select')].find(el => el.parentElement.textContent.startsWith('Procedencia'));
        select.value = ${JSON.stringify(value)};
        select.dispatchEvent(new Event('change', { bubbles: true }));
      })()`);
      await setProvenance("manual");
      await wait(text("No existen registros para este período"));
      await control({ failHistory: true });
      await setProvenance("demo");
      await wait(text("No se pudo cargar el histórico"));
      await click("Reintentar consulta");
      await wait(text("Eventos por procedencia"));
      await evaluate(
        "document.querySelector('main a[href*=source_sha256]').click()",
      );
      await wait(
        "location.pathname==='/events' && location.search.includes('source_sha256=') && location.search.includes('source_kind=demo')",
      );
      await wait(text("1 evento registrado"));
      await wait(text("Video filtrado"));
      await click("Ver evidencia");
      await wait("document.querySelector('.event-preview video')?.preload==='none'");
      await wait("[...document.querySelectorAll('.event-preview img')].some(img=>img.naturalWidth>0)");
      await evaluate(
        "document.querySelector('.event-preview a').click()",
      );
      await wait(text("Resumen operacional"));
      assert.ok(await evaluate(
        "document.querySelector('main a[href*=\"source_kind=demo\"]')?.href.includes('source_sha256=')",
      ));
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
          await wait("!!document.querySelector('main#main-content')");
          if (route === "/events") await wait(text("Proximidad persona"));
          if (route === "/") await wait(text("Actividad reciente"));
          if (route === "/indicators")
            await wait(text("Eventos por procedencia"));
          if (route === `/events/${eventId}`) {
            await wait(
              text("requiere revisión humana, no confirma un incidente"),
            );
          }
          if (route === "/analysis") await wait(text("Análisis detenido"));
          await wait("document.fonts.status==='loaded'");
          try {
            await checkButtonThemes(evaluate);
          } catch (error) {
            throw new Error(`Controles de tema: ${width} ${route}`, {
              cause: error,
            });
          }
          assert.equal(
            await evaluate(
              "document.documentElement.scrollWidth<=innerWidth+1",
            ),
            true,
            `Overflow: ${width} ${route}`,
          );
        }
      }
      await checkButtonThemes(evaluate, call);
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
      await viewport(1440);
      await control({ expire: true });
      await evaluate(
        "document.querySelector('nav a[href=\"/events\"]').click()",
      );
      await wait("location.pathname==='/login'");
      await wait(text("Tu sesión terminó."));
      await credentials("TEST_ONLY_PASSWORD");
      await wait("location.pathname==='/events'");
      await evaluate(`(${accountTrigger}).click()`);
      await click("Cerrar sesión");
      await wait("location.pathname==='/login'");
      await go("/events");
      await wait("location.pathname==='/login'");
      await go("/login?next=%2F%5Cexample.invalid%2F");
      await credentials("TEST_ONLY_PASSWORD");
      await wait("location.pathname==='/'");
      assert.equal(await evaluate("location.origin"), new URL(base).origin);
      await control({ demoCMissing: true });
      await evaluate("sessionStorage.clear()");
      await go("/analysis?profile=B");
      await wait("!!document.querySelector('.analysis-stage video')");
      const beforeMissingDemo = await control();
      await evaluate("document.querySelectorAll('.analysis-profiles button')[2].click()");
      await wait(text("El Perfil C no tiene una demo disponible"));
      assert.equal((await control()).deleted, beforeMissingDemo.deleted);
      assert.equal(await evaluate(
        "document.querySelectorAll('.analysis-profiles button')[1].getAttribute('aria-pressed')",
      ), "true");
      assert.ok(await evaluate("!!document.querySelector('.analysis-stage video')"));
      await evaluate("sessionStorage.clear()");
      await go("/analysis?profile=C");
      await wait(text("Perfil C · demo no disponible"));
      assert.ok(await evaluate("!!document.querySelector('.analysis-contextbar input[type=file]')"));
      await evaluate(`(${accountTrigger}).click()`);
      await click("Cerrar sesión");
      await wait("location.pathname==='/login'");
      await evaluate(`(() => {
        document.querySelector('#login-username').value = 'fixture-viewer';
        document.querySelector('#login-password').value = 'TEST_ONLY_RESET_PASSWORD';
      })()`);
      await click("Ingresar");
      await wait("location.pathname==='/indicators'");
      await wait(text("Sin eventos de cargas manuales"));
      await wait("!!document.querySelector('#operix-sidebar a[href=\"/indicators\"]')");
      assert.equal(await evaluate("!!document.querySelector('#operix-sidebar a[href=\"/analysis\"]')"), false);
      assert.deepEqual(
        await evaluate(`Promise.all([
          fetch('/api/v1/users/'), fetch('/api/v1/events/'), fetch('/api/v1/analysis/profiles/')
        ]).then(items=>items.map(item=>item.status))`),
        [403, 403, 403],
      );
      await go("/analysis");
      await wait("location.pathname==='/indicators'");
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
