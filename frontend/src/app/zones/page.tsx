import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { PageTitle } from "@/components/layout/page-title";

export default function ZonesPage() {
  return (
    <div className="page-wrap operational-page">
      <header className="app-page-heading">
        <div>
          <PageTitle>Zonas del video</PageTitle>
          <p>
            Marca las áreas donde Operix debe evaluar una regla, como un pasillo
            o una zona de acceso restringido.
          </p>
        </div>
      </header>
      <section
        className="zones-guide surface-card"
        aria-labelledby="zones-guide-title"
      >
        <h2 id="zones-guide-title">Configura una zona desde el video</h2>
        <ol>
          <li>Selecciona un video o una demo en Análisis.</li>
          <li>Abre «Zonas, calibración y reglas» y dibuja el área.</li>
          <li>Asocia una regla y guarda la configuración para esa fuente.</li>
        </ol>
        <Link className="button button-primary" href="/analysis">
          Ir a Análisis <ArrowRight size={15} aria-hidden="true" />
        </Link>
      </section>
    </div>
  );
}
