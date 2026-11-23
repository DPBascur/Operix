import { PageTitle } from "@/components/layout/page-title";
import { CameraWorkspace } from "@/features/sources/camera-workspace";

export const metadata = { title: "Centro de monitoreo" };

export default function MonitoringPage() {
  return (
    <div className="sources-page page-v1">
      <header className="page-hero compact app-page-heading">
        <div>
          <PageTitle>Centro de monitoreo</PageTitle>
          <p>Observa las cámaras en una sola vista.</p>
        </div>
      </header>
      <CameraWorkspace monitor />
    </div>
  );
}
