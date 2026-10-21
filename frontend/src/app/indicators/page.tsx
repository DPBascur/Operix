import { AppShell } from "@/components/layout/app-shell";

const prerequisites = [
  ["Histórico", "Resultados comparables entre sesiones"],
  ["Persistencia", "Series temporales verificables"],
  ["Definición", "Indicadores y umbrales acordados"],
];

export default function IndicatorsPage() {
  return (
    <AppShell activePath="/indicators">
      <div className="page-wrap operational-page">
        <header className="compact-page-header">
          <div>
            <h2 className="compact-page-title">Indicadores</h2>
            <p className="compact-page-copy">
              Esta vista se habilitará cuando existan datos históricos válidos.
            </p>
          </div>
          <span className="source-indicator">Sin histórico</span>
        </header>

        <section
          className="indicators-empty"
          aria-labelledby="indicators-title"
        >
          <div className="max-w-xl">
            <p className="section-heading">Estado de datos</p>
            <h2 id="indicators-title">
              No hay resultados agregados que mostrar
            </h2>
            <p>
              Operix no convierte datos de demostración en métricas. Los
              indicadores aparecerán cuando Backend y definición técnica
              permitan afirmaciones reproducibles.
            </p>
          </div>
          <dl className="readiness-list">
            {prerequisites.map(([term, detail]) => (
              <div key={term}>
                <dt>{term}</dt>
                <dd>{detail}</dd>
              </div>
            ))}
          </dl>
        </section>
      </div>
    </AppShell>
  );
}
