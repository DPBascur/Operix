import { PageTitle } from "@/components/layout/page-title";
import { SourceCatalog } from "@/features/sources/source-catalog";

export const metadata = { title: "Fuentes" };

export default function SourcesPage() {
  return (
    <div className="sources-page page-v1">
      <header className="page-hero compact app-page-heading">
        <div>
          <PageTitle>Fuentes</PageTitle>
          <p>Selecciona una cámara o abre un video para analizar.</p>
        </div>
      </header>
      <SourceCatalog />
    </div>
  );
}
