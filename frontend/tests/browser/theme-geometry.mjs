import assert from "node:assert/strict";

// Compara geometría computada, sin fijar píxeles ni depender del orden del CSS.
// Las rutas ejercitan controles reales; el muestrario cubre variantes/estados
// del contrato Button que no aparecen simultáneamente en una sola pantalla.
export async function checkButtonThemes(evaluate, call) {
  const original = await evaluate("document.documentElement.dataset.theme");
  const measure = (selector) =>
    evaluate(`(() => {
    return [...document.querySelectorAll(${JSON.stringify(selector)})]
      .filter(el => el.getClientRects().length).map(el => {
        const s = getComputedStyle(el);
        // Un flex que rellena su panel hereda el ancho disponible; se compara
        // su contrato flex, no el ancho cromático del contenedor ajeno a Button.
        const width = Number(s.flexGrow) > 0 ? 'flex:' + s.flex : s.width;
        return [s.borderRadius, s.height, width, s.padding, s.fontSize,
          s.fontWeight, s.lineHeight, s.display, s.gap, s.borderWidth];
      });
  })()`);
  const compare = async (selector, label) => {
    const results = [];
    for (const theme of ["light", "dark"]) {
      await evaluate(
        `document.documentElement.dataset.theme=${JSON.stringify(theme)}`,
      );
      results.push(await measure(selector));
    }
    assert.ok(results[0].length, `Sin controles: ${label}`);
    assert.deepEqual(results[0], results[1], `Geometría light/dark: ${label}`);
  };
  try {
    await compare(".button", "controles de la ruta");
    if (!call) return;
    await evaluate(`(() => {
      const host = document.createElement('section');
      host.id = 'theme-test-controls'; host.className = 'refresh-shell';
      host.style.cssText = 'position:fixed;inset:0;z-index:9999;overflow:auto;background:var(--surface)';
      for (const variant of ['primary','secondary','outline','ghost','destructive']) {
        for (const size of ['default','small','icon']) {
          for (const state of ['default','disabled','loading']) {
            const button = document.createElement('button');
            button.className = 'button button-' + variant + ' button-size-' + size;
            button.textContent = size === 'icon' ? '+' : 'Acción';
            button.disabled = state !== 'default';
            if (state === 'loading') {
              button.setAttribute('aria-busy','true');
              const spinner = document.createElement('span');
              spinner.className = 'spinner'; spinner.setAttribute('aria-hidden','true');
              button.prepend(spinner);
            }
            host.append(button);
          }
        }
      }
      document.body.append(host);
    })()`);
    await compare(
      "#theme-test-controls .button",
      "variantes, tamaños, disabled/loading",
    );
    await call("DOM.enable");
    await call("CSS.enable");
    const { root } = await call("DOM.getDocument");
    const { nodeIds } = await call("DOM.querySelectorAll", {
      nodeId: root.nodeId,
      selector: "#theme-test-controls .button:not(:disabled)",
    });
    for (const pseudoClasses of [
      ["hover"],
      ["active"],
      ["focus", "focus-visible"],
    ]) {
      for (const nodeId of nodeIds)
        await call("CSS.forcePseudoState", {
          nodeId,
          forcedPseudoClasses: pseudoClasses,
        });
      await compare("#theme-test-controls .button", pseudoClasses.join("/"));
      if (pseudoClasses.includes("focus-visible")) {
        for (const theme of ["light", "dark"]) {
          await evaluate(`document.documentElement.dataset.theme='${theme}'`);
          assert.equal(
            await evaluate(`([...document.querySelectorAll('#theme-test-controls .button:not(:disabled)')].every(el => {
            const s = getComputedStyle(el);
            return s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0 && parseFloat(s.outlineOffset) > 0;
          }))`),
            true,
            `Foco visible: ${theme}`,
          );
        }
      }
    }
    for (const nodeId of nodeIds)
      await call("CSS.forcePseudoState", { nodeId, forcedPseudoClasses: [] });
  } finally {
    await evaluate(`document.querySelector('#theme-test-controls')?.remove();
      ${original ? `document.documentElement.dataset.theme=${JSON.stringify(original)}` : "delete document.documentElement.dataset.theme"}`);
  }
}
