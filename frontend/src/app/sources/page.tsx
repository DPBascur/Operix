import { AppShell } from "@/components/layout/app-shell";
import { SourceCatalog } from "@/features/sources/source-catalog";

export default function SourcesPage() {
  return (
    <AppShell activePath="/sources">
      <div className="sources-page page-v1">
        <header className="page-hero compact">
          <div>
            <span className="eyebrow">Catálogo operacional</span>
            <h2>Fuentes</h2>
            <p>Videos, demos y futuras cámaras disponibles para análisis.</p>
          </div>
        </header>
        <SourceCatalog />
      </div>
    </AppShell>
  );
}
