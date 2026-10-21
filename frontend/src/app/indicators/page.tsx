import { AppShell } from "@/components/layout/app-shell";
import { IndicatorFrequencies } from "@/features/indicators/indicator-frequencies";

export default function IndicatorsPage() {
  return (
    <AppShell activePath="/indicators">
      <div className="page-wrap operational-page">
        <header className="compact-page-header">
          <div>
            <h2 className="compact-page-title">Indicadores</h2>
            <p className="compact-page-copy">
              Frecuencias por período y tipo, reconciliadas con los registros de
              la API.
            </p>
          </div>
          <span className="source-indicator">Consulta de registros</span>
        </header>

        <IndicatorFrequencies />
      </div>
    </AppShell>
  );
}
