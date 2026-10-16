import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/ui/page-header";
import { AnalysisWorkspace } from "@/features/analysis/analysis-workspace";

export default function AnalysisPage() {
  return (
    <AppShell activePath="/analysis">
      <div className="mx-auto max-w-[1500px] space-y-6 px-4 py-6 sm:px-6 sm:py-8 lg:px-8 lg:py-10">
        <PageHeader
          description="Seleccione un video local, ajuste la zona y observe el procesamiento del Motor."
          eyebrow="Espacio operativo"
          title="Análisis de video"
        />
        <AnalysisWorkspace />
      </div>
    </AppShell>
  );
}
