import { AppShell } from "@/components/layout/app-shell";
import { MockDataNotice } from "@/components/ui/mock-data-notice";
import { PageHeader } from "@/components/ui/page-header";
import { AnalysisWorkspace } from "@/features/analysis/analysis-workspace";

export default function AnalysisPage() {
  return (
    <AppShell activePath="/analysis">
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 sm:py-8 lg:px-8 lg:py-10">
        <PageHeader
          description="Previsualización del espacio operativo con información simulada del frontend."
          eyebrow="Espacio operativo"
          title="Análisis de video"
        />
        <MockDataNotice />
        <AnalysisWorkspace />
      </div>
    </AppShell>
  );
}
