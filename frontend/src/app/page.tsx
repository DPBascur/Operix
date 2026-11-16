import { HistoricalDashboard } from "@/features/dashboard/historical-dashboard";

export const metadata = { title: { absolute: "Centro operativo · Operix" } };

export default function HomePage() {
  return <HistoricalDashboard overview />;
}
