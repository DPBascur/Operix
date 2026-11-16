"use client";

import { useEffect, useState, type ComponentProps } from "react";
import { Button } from "@/components/ui/button";
import { useSession } from "@/features/auth/session-provider";
import { apiFetch } from "@/services/browser-session";
import { eventTypeName } from "@/services/event-contract";
import { HistoricalDashboard } from "./historical-dashboard";
import { parseFrequency, type EventFrequency } from "./history-model";

export function IndicatorsAccess(
  props: ComponentProps<typeof HistoricalDashboard>,
) {
  const { user } = useSession();
  return user?.role === "viewer" ? (
    <SharedIndicators initialMonth={props.initialMonth} />
  ) : (
    <HistoricalDashboard {...props} />
  );
}

function SharedIndicators({ initialMonth }: { initialMonth?: string }) {
  const currentMonth = new Date().toISOString().slice(0, 7);
  const [month, setMonth] = useState(initialMonth ?? currentMonth);
  const [state, setState] = useState<{
    month: string;
    data?: EventFrequency;
    error?: string;
  }>();
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const request = new AbortController();
    const params = new URLSearchParams({ month });
    apiFetch("/api/v1/indicators/shared/?" + params, {
      cache: "no-store",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(12000)]),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        const data = parseFrequency(await response.json());
        if (!request.signal.aborted) setState({ month, data });
      })
      .catch(() => {
        if (!request.signal.aborted)
          setState({ month, error: "No se pudieron cargar los indicadores." });
      });
    return () => request.abort();
  }, [month, revision]);

  const result = state?.month === month ? state : undefined;
  const frequency = result?.data;
  const maxDailyCount = frequency
    ? Math.max(1, ...frequency.by_period.map((item) => item.count))
    : 1;

  return (
    <section className="page-wrap identity-page">
      <header className="identity-heading directory-heading">
        <div>
          <h2 className="compact-page-title">Indicadores de eventos</h2>
          <p>
            Conteos por día y condición configurada satisfecha. Las cargas
            manuales pueden incluir ensayos.
          </p>
        </div>
        <label className="shared-period" htmlFor="shared-indicator-month">
          Mes UTC
          <input
            className="input"
            type="month"
            id="shared-indicator-month"
            value={month}
            max={currentMonth}
            onChange={(event) => {
              if (
                /^[1-9][0-9]{3}-(0[1-9]|1[0-2])$/.test(event.target.value) &&
                event.target.value <= currentMonth
              ) {
                setMonth(event.target.value);
              }
            }}
          />
        </label>
      </header>
      {!result && <p role="status">Cargando indicadores…</p>}
      {result?.error && (
        <div role="alert">
          <p>{result.error}</p>
          <Button
            variant="outline"
            onClick={() => {
              setState(undefined);
              setRevision(revision + 1);
            }}
          >
            Reintentar
          </Button>
        </div>
      )}
      {frequency && (
        <>
          <div className="shared-total">
            <strong>{frequency.total}</strong> eventos registrados
          </div>
          {frequency.total === 0 ? (
            <p>Sin eventos de cargas manuales para el período seleccionado.</p>
          ) : (
            <div className="shared-indicator-grid">
              <section className="identity-panel">
                <h3>Frecuencia diaria</h3>
                <ul className="shared-frequency">
                  {frequency.by_period.map(({ date, count }) => (
                    <li key={date}>
                      <time dateTime={date}>
                        {date.slice(8)}/{date.slice(5, 7)}
                      </time>
                      <progress
                        aria-label={"Eventos del " + date}
                        value={count}
                        max={maxDailyCount}
                      />
                      <strong>{count}</strong>
                    </li>
                  ))}
                </ul>
              </section>
              <section className="identity-panel">
                <h3>Por tipo de evento</h3>
                <ul className="shared-frequency">
                  {frequency.by_type.map(({ event_type, count }) => (
                    <li key={event_type}>
                      <span>{eventTypeName(event_type)}</span>
                      <strong>{count}</strong>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          )}
        </>
      )}
    </section>
  );
}
