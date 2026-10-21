import { AppShell } from "@/components/layout/app-shell";
import { AnalysisWorkspace } from "@/features/analysis/analysis-workspace";

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
    <AppShell activePath="/analysis">
      <div className="analysis-page">
        <AnalysisWorkspace
          initialProfile={initialProfile}
          initialManual={params.source === "manual"}
        />
      </div>
    </AppShell>
  );
}
