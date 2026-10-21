import { CircleCheck } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { RecentActivity } from "@/features/home/recent-activity";
import { SourceCatalog } from "@/features/sources/source-catalog";

export default function HomePage() {
  return (
    <AppShell activePath="/">
      <div className="home-v1 page-v1">
        <header className="page-hero home-hero">
          <div>
            <span className="eyebrow">Operación local</span>
            <h2>Centro operativo</h2>
            <p>
              Prepare una fuente, ejecute el análisis y revise la evidencia
              generada.
            </p>
          </div>
          <div className="system-availability">
            <CircleCheck aria-hidden="true" />
            <div>
              <strong>Entorno local disponible</strong>
              <span>Servicios preparados para una sesión</span>
            </div>
          </div>
        </header>

        <SourceCatalog compact />
        <RecentActivity />
      </div>
    </AppShell>
  );
}
