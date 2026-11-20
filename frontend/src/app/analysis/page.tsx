import { AnalysisWorkspace } from "@/features/analysis/analysis-workspace";
import { PageTitle } from "@/components/layout/page-title";

export const metadata = { title: "Análisis de video" };

export default async function AnalysisPage({
  searchParams,
}: {
  searchParams: Promise<{
    profile?: string;
    source?: string;
    configure?: string;
    session?: string;
    sha?: string;
  }>;
}) {
  const params = await searchParams;
  const { profile } = params;
  const profileRequested = profile === "A" || profile === "B" || profile === "C";
  const initialProfile = profileRequested ? profile : "A";
  const requestedSessionId = typeof params.session === "string" &&
    /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(params.session)
    ? params.session : undefined;
  const requestedSourceSha = typeof params.sha === "string" && /^[0-9a-f]{64}$/i.test(params.sha)
    ? params.sha : undefined;
  return (
    <div className="analysis-page">
      <header className="app-page-heading">
        <PageTitle>Análisis de video</PageTitle>
      </header>
      <AnalysisWorkspace
        initialProfile={initialProfile}
        initialManual={params.source === "manual"}
        profileRequested={profileRequested}
        initialConfigure={params.configure === "1"}
        requestedSessionId={requestedSessionId}
        requestedSourceSha={requestedSourceSha}
      />
    </div>
  );
}
