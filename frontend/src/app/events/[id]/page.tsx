import { EventDetail } from "@/features/events/event-detail";

export const metadata = { title: "Expediente de evento" };

export default async function EventDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ back?: string | string[] }>;
}) {
  const [{ id }, { back }] = await Promise.all([params, searchParams]);
  const returnUrl =
    typeof back === "string" && back.startsWith("/events?") ? back : "/events";
  return <EventDetail key={id} id={id} returnUrl={returnUrl} />;
}
