import { IndicatorsAccess } from "@/features/dashboard/indicators-access";
export default async function IndicatorsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { month, type, source } = await searchParams;
  const selection = {
    initialMonth:
      typeof month === "string" &&
      /^[1-9][0-9]{3}-(0[1-9]|1[0-2])$/.test(month) &&
      month <= new Date().toISOString().slice(0, 7)
        ? month
        : undefined,
    initialType:
      typeof type === "string" &&
      [
        "zone_dwell",
        "person_forklift_proximity",
        "zone_entry",
        "zone_coexistence",
      ].includes(type ?? "")
        ? type
        : undefined,
    initialSource:
      source === "demo" || source === "manual" || source === "unknown"
        ? source
        : undefined,
  };
  return <IndicatorsAccess key={JSON.stringify(selection)} {...selection} />;
}
