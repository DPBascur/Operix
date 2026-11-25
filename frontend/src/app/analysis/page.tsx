import { AnalysisWorkspace } from "@/features/analysis/analysis-workspace";
import { PageTitle } from "@/components/layout/page-title";
import { ArrowRight, Camera } from "lucide-react";
import Link from "next/link";

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
    suite?: string;
  }>;
}) {
  const params = await searchParams;
  const { profile } = params;
  const profileRequested =
    profile === "A" || profile === "B" || profile === "C";
  const initialProfile = profileRequested ? profile : "A";
  const initialManual = params.source === "manual";
  const requestedSessionId =
    typeof params.session === "string" &&
    /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(params.session)
      ? params.session
      : undefined;
  const requestedSourceSha =
    typeof params.sha === "string" && /^[0-9a-f]{64}$/i.test(params.sha)
      ? params.sha
      : undefined;
  return (
    <div className="analysis-page">
      <header className="app-page-heading">
        <PageTitle>Análisis de video</PageTitle>
      </header>
      {!profileRequested &&
        !initialManual &&
        !requestedSessionId &&
        !requestedSourceSha && (
          <section
            className="surface-card mb-4 flex flex-wrap items-center justify-between gap-3 p-4"
            aria-labelledby="analysis-camera-title"
          >
            <div>
              <h2 id="analysis-camera-title" className="font-semibold">
                Cámaras virtuales
              </h2>
              <p className="text-sm text-text-secondary">
                Consulta el monitoreo y los fotogramas recientes del
                laboratorio.
              </p>
            </div>
            <Link
              className="button button-outline"
              href="/sources#laboratorio-camaras"
            >
              <Camera aria-hidden="true" /> Ver cámaras{" "}
              <ArrowRight aria-hidden="true" />
            </Link>
          </section>
        )}
      <AnalysisWorkspace
        key={params.suite === "simulation" ? "simulation" : "real"}
        suite={params.suite === "simulation" ? "simulation" : "real"}
        initialProfile={initialProfile}
        initialManual={initialManual}
        profileRequested={profileRequested}
        initialConfigure={params.configure === "1"}
        requestedSessionId={requestedSessionId}
        requestedSourceSha={requestedSourceSha}
      />
    </div>
  );
}
