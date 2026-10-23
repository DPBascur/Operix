import { AppShell } from "@/components/layout/app-shell";
import { HistoricalDashboard } from "@/features/dashboard/historical-dashboard";

export default function HomePage() {
  return (
    <AppShell activePath="/">
      <HistoricalDashboard />
    </AppShell>
  );
}
