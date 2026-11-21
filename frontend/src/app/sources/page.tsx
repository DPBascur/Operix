import { PageTitle } from "@/components/layout/page-title";
import { SourceCatalog } from "@/features/sources/source-catalog";

export const metadata = { title: "Fuentes" };

export default function SourcesPage() {
  return (
    <div className="sources-page page-v1">
      <header className="page-hero compact app-page-heading">
        <div>
          <span className="eyebrow">Catálogo operacional</span>
          <PageTitle>Fuentes</PageTitle>
          <p>Videos, demos y cámaras de laboratorio para análisis.</p>
        </div>
      </header>
      <SourceCatalog />
    </div>
  );
}
