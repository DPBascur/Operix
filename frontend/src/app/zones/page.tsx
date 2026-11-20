import { PageTitle } from "@/components/layout/page-title";
import { ZoneInventory } from "@/features/operations/zone-inventory";

export const metadata = { title: "Zonas" };

export default function ZonesPage() {
  return (
    <div className="page-wrap operational-page">
      <header className="app-page-heading">
        <div>
          <PageTitle>Zonas del video</PageTitle>
          <p>
            Consulta las zonas y reglas vinculadas a cada fuente y abre el
            editor para revisar su geometría.
          </p>
        </div>
      </header>
      <ZoneInventory />
    </div>
  );
}
