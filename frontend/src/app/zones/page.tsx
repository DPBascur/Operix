import { ArrowRight, Crosshair } from "lucide-react";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";

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
          <Link className="button button-primary" href="/analysis">
            Editar zona en Análisis <ArrowRight size={15} aria-hidden="true" />
          </Link>
        </header>

        <section
          className="zone-workbench"
          aria-labelledby="zone-workbench-title"
        >
          <div className="zone-preview">
            <div className="zone-preview-crosshair" aria-hidden="true">
              <Crosshair size={24} strokeWidth={1.4} />
            </div>
            <div className="zone-preview-copy">
              <h2 id="zone-workbench-title">Edite la zona sobre su video</h2>
              <p>
                Abra Análisis para preparar una fuente o retomar su sesión.
                Puede crear vértices por coordenadas y ajustarlos con el
                teclado.
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
          </aside>
        </section>
      </div>
    </AppShell>
  );
}
