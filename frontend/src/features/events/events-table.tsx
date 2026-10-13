"use client";

import { Activity, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/status-badge";
import { mockEventRows } from "@/mocks/ui-data";

export function EventsTable() {
  const [query, setQuery] = useState("");
  const [zone, setZone] = useState("all");
  const filteredEvents = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("es");
    return mockEventRows.filter((event) => {
      const matchesQuery =
        !normalizedQuery ||
        event.title.toLocaleLowerCase("es").includes(normalizedQuery) ||
        event.rule.toLocaleLowerCase("es").includes(normalizedQuery);
      return matchesQuery && (zone === "all" || event.zone === zone);
    });
  }, [query, zone]);

  return (
    <>
      <div className="flex flex-col gap-3 sm:flex-row">
        <label className="flex flex-1 items-center gap-2 rounded-control border border-border bg-surface px-3 py-2.5 text-sm text-text-secondary focus-within:border-brand-accent">
          <Search aria-hidden="true" size={17} />
          <span className="sr-only">Buscar evento o regla</span>
          <Input
            className="!min-h-0 !border-0 !bg-transparent !p-0 text-foreground"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar evento o regla"
            type="search"
            value={query}
          />
        </label>
        <label className="grid gap-1 text-xs font-medium text-text-secondary">
          <span className="sr-only">Filtrar por zona</span>
          <select
            className="h-full min-h-10 rounded-control border border-border bg-surface px-3 text-sm text-foreground"
            onChange={(event) => setZone(event.target.value)}
            value={zone}
          >
            <option value="all">Todas las zonas</option>
            {["Zona A", "Zona B", "Zona C", "Zona D"].map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="mt-4 flex min-h-11 items-center justify-between gap-3">
        <p role="status" className="text-xs text-text-secondary">
          {filteredEvents.length}{" "}
          {filteredEvents.length === 1
            ? "candidato simulado"
            : "candidatos simulados"}
        </p>
        {(query || zone !== "all") && (
          <Button
            variant="ghost"
            onClick={() => {
              setQuery("");
              setZone("all");
            }}
          >
            Limpiar filtros
          </Button>
        )}
      </div>
      <ul
        aria-label="Eventos simulados"
        className="divide-y divide-border xl:hidden"
      >
        {filteredEvents.map((event) => (
          <li className="py-4 first:pt-1 last:pb-0" key={event.id}>
            <div className="flex items-start gap-3">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-control bg-brand-accent/10 text-accent">
                <Activity aria-hidden="true" size={17} />
              </span>
              <div className="min-w-0 flex-1">
                <h2 className="text-sm font-semibold text-foreground">
                  {event.title}
                </h2>
                <time
                  className="mt-1 block text-xs tabular-nums text-text-secondary"
                  dateTime={event.time}
                >
                  {event.time}
                </time>
              </div>
              <StatusBadge tone={event.tone}>{event.status}</StatusBadge>
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 pl-12 text-xs">
              <div>
                <dt className="text-text-secondary">Zona</dt>
                <dd className="mt-0.5 font-medium text-foreground">
                  {event.zone}
                </dd>
              </div>
              <div>
                <dt className="text-text-secondary">Regla</dt>
                <dd className="mt-0.5 font-medium text-foreground">
                  {event.rule}
                </dd>
              </div>
              <div>
                <dt className="text-text-secondary">Objetos</dt>
                <dd className="mt-0.5 font-medium text-foreground">
                  No informados
                </dd>
              </div>
              <div>
                <dt className="text-text-secondary">Confianza mock</dt>
                <dd className="mt-0.5 font-medium tabular-nums text-foreground">
                  {event.confidence.toLocaleString("es-CL", {
                    style: "percent",
                  })}
                </dd>
              </div>
            </dl>
          </li>
        ))}
      </ul>
      <div
        className="mt-2 hidden overflow-x-auto rounded-control focus-visible:outline-accent xl:block"
        role="region"
        aria-label="Tabla de eventos simulados; desplazamiento horizontal disponible"
        tabIndex={0}
      >
        <table className="w-full min-w-180 text-left text-sm">
          <caption className="sr-only">Candidatos de evento simulados</caption>
          <thead className="border-b border-border text-xs uppercase tracking-wide text-text-secondary">
            <tr>
              {[
                "Evento",
                "Zona",
                "Regla",
                "Objetos",
                "Confianza",
                "Hora",
                "Estado",
              ].map((heading) => (
                <th
                  className="px-3 py-3 font-semibold"
                  key={heading}
                  scope="col"
                >
                  {heading}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filteredEvents.map(
              ({
                id,
                title,
                zone: eventZone,
                rule,
                confidence,
                time,
                status,
                tone,
              }) => (
                <tr
                  className="transition-colors hover:bg-brand-accent/5"
                  key={id}
                >
                  <td className="px-3 py-4">
                    <div className="flex items-center gap-3">
                      <span className="flex size-9 items-center justify-center rounded-control bg-brand-accent/10 text-accent">
                        <Activity aria-hidden="true" size={17} />
                      </span>
                      <span className="font-semibold text-foreground">
                        {title}
                      </span>
                    </div>
                  </td>
                  <td className="px-3 py-4 text-text-secondary">{eventZone}</td>
                  <td className="px-3 py-4 font-medium text-primary">{rule}</td>
                  <td className="px-3 py-4 text-xs text-text-secondary">
                    No informados
                  </td>
                  <td className="px-3 py-4 tabular-nums">
                    {confidence.toLocaleString("es-CL", { style: "percent" })}
                  </td>
                  <td className="px-3 py-4 tabular-nums text-text-secondary">
                    {time}
                  </td>
                  <td className="px-3 py-4">
                    <StatusBadge tone={tone}>{status}</StatusBadge>
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      </div>
      {filteredEvents.length === 0 ? (
        <p className="py-10 text-center text-sm text-text-secondary">
          No hay coincidencias en los datos mock.
        </p>
      ) : null}
    </>
  );
}
