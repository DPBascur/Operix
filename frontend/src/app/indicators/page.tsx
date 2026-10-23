import { AppShell } from "@/components/layout/app-shell";
import { HistoricalDashboard } from "@/features/dashboard/historical-dashboard";
export default function IndicatorsPage() {
  return (
    <AppShell activePath="/indicators">
      <HistoricalDashboard />
    </AppShell>
  );
}
