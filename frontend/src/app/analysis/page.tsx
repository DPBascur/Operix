import { AnalysisWorkspace } from "@/features/analysis/analysis-workspace";
import { PageTitle } from "@/components/layout/page-title";

export const metadata = { title: "Análisis de video" };

export default async function AnalysisPage({
  searchParams,
}: {
  searchParams: Promise<{ profile?: string; source?: string }>;
}) {
  const params = await searchParams;
  const initialProfile = ["A", "B", "C"].includes(params.profile ?? "")
    ? (params.profile as "A" | "B" | "C")
    : "A";
  return (
    <div className="analysis-page">
      <header className="app-page-heading">
        <PageTitle>Análisis de video</PageTitle>
      </header>
      <AnalysisWorkspace
        initialProfile={initialProfile}
        initialManual={params.source === "manual"}
      />
    </div>
  );
}
