import { ArrowRight, Crosshair } from "lucide-react";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { MockDataNotice } from "@/components/ui/mock-data-notice";

export default function ZonesPage() {
  return (
    <AppShell activePath="/zones">
      <div className="page-wrap operational-page">
        <header className="compact-page-header">
          <div>
            <h2 className="compact-page-title">Contexto espacial</h2>
            <p className="compact-page-copy">
              La geometría se define sobre la fuente que será analizada.
            </p>
          </div>
          <span className="source-indicator">Sin video conectado</span>
        </header>
        <MockDataNotice />

        <section
          className="zone-workbench"
          aria-labelledby="zone-workbench-title"
        >
          <div className="zone-preview">
            <div className="zone-preview-crosshair" aria-hidden="true">
              <Crosshair size={24} strokeWidth={1.4} />
            </div>
            <div className="zone-preview-copy">
              <h2 id="zone-workbench-title">Vista espacial no disponible</h2>
              <p>
                Abra una fuente para editar el polígono en su contexto visual.
              </p>
            </div>
          </div>
          <aside className="zone-properties" aria-label="Propiedades de zona">
            <div>
              <p className="section-heading">Flujo</p>
              <ol className="zone-steps">
                <li>
                  <span>1</span>
                  <div>
                    <strong>Fuente</strong>
                    <small>Video o demo</small>
                  </div>
                </li>
                <li>
                  <span>2</span>
                  <div>
                    <strong>Zona</strong>
                    <small>Polígono normalizado</small>
                  </div>
                </li>
                <li>
                  <span>3</span>
                  <div>
                    <strong>Regla</strong>
                    <small>Contexto operacional</small>
                  </div>
                </li>
              </ol>
            </div>
            <Link className="button button-primary" href="/analysis">
              Abrir análisis <ArrowRight size={15} aria-hidden="true" />
            </Link>
          </aside>
        </section>
      </div>
    </AppShell>
  );
}
