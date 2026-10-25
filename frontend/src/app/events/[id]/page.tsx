"use client";

import { useParams } from "next/navigation";
import { EventDetail } from "@/features/events/event-detail";

export default function EventDetailPage() {
  const { id } = useParams<{ id: string }>();
  return <EventDetail key={id} id={id} />;
}
