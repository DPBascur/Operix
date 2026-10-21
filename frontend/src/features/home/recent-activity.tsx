"use client";

import { ArrowRight, Clock3 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { environment } from "@/config/environment";
import { eventsService } from "@/services/events.service";
import type { EventListItem } from "@/types/operix";

export function RecentActivity() {
  const [events, setEvents] = useState<EventListItem[]>([]);
  const [loading, setLoading] = useState(environment.dataSource === "api");

  useEffect(() => {
    if (environment.dataSource !== "api") return;
    let active = true;
    eventsService
      .listRows({})
      .then(
        (items) => {
          if (active) setEvents(items.slice(0, 3));
        },
        () => {
          if (active) setEvents([]);
        },
      )
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <section
      className="recent-activity"
      aria-labelledby="recent-activity-title"
    >
      <div className="section-intro">
        <div>
          <span className="eyebrow">Trazabilidad</span>
          <h2 id="recent-activity-title">Actividad reciente</h2>
        </div>
        <Link href="/events">
          Abrir eventos <ArrowRight aria-hidden="true" />
        </Link>
      </div>
      {loading ? (
        <p className="recent-empty">Consultando actividad local…</p>
      ) : events.length ? (
        <ul className="recent-list">
          {events.map((event) => (
            <li key={event.id}>
              <Clock3 aria-hidden="true" />
              <div>
                <strong>{event.title}</strong>
                <span>
                  {event.zone} · {event.objects}
                </span>
              </div>
              <time>{event.time}</time>
            </li>
          ))}
        </ul>
      ) : (
        <p className="recent-empty">
          No existe actividad real registrada para mostrar.
        </p>
      )}
    </section>
  );
}
