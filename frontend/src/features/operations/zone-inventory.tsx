"use client";

import { useEffect, useState } from "react";
import { ArrowRight, MapPinned } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { OperixScanLoader } from "@/components/ui/operix-scan-loader";
import { formatHistoryTime } from "@/features/dashboard/history-model";
import { operationalError, operationalRequest } from "./operation-request";
import { ruleTypes, type RegisteredSource } from "./policy-model";
import styles from "./operations.module.css";

function sourceLabel(source: RegisteredSource) {
  return source.filename ?? `Fuente ${source.source_sha256.slice(0, 12)}`;
}

function analysisHref(source: RegisteredSource) {
  const query = new URLSearchParams({
    configure: "1",
    sha: source.source_sha256,
  });
  if (source.profile) query.set("profile", source.profile);
  if (source.session_id) query.set("session", source.session_id);
  if (source.source_kind !== "demo") query.set("source", "manual");
  return `/analysis?${query}`;
}

export function ZoneInventory() {
  const [inventory, setInventory] = useState<RegisteredSource[] | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [selected, setSelected] = useState("");

  useEffect(() => {
    let active = true;
    operationalRequest<{ sources: RegisteredSource[] }>("sources/").then(
      ({ sources }) => {
        if (active) setInventory(sources);
      },
      (cause: unknown) => {
        if (active) setError(operationalError(cause));
      },
    );
    return () => {
      active = false;
    };
  }, [attempt]);

  if (error)
    return (
      <section className="surface-card p-4">
        <p role="alert">{error}</p>
        <Button
          variant="outline"
          onClick={() => {
            setError("");
            setAttempt((attempt) => attempt + 1);
          }}
        >
          Reintentar consulta
        </Button>
      </section>
    );
  if (!inventory)
    return <OperixScanLoader variant="panel" message="Cargando zonas…" />;
  if (!inventory.length)
    return (
      <section className="surface-card grid gap-3 p-5">
        <MapPinned size={22} aria-hidden="true" />
        <h2 className="text-lg font-semibold">
          Prepara una fuente para empezar
        </h2>
        <p>
          Al abrir un video, sus zonas y revisiones quedan disponibles en este
          inventario.
        </p>
        <Link className="button button-primary w-fit" href="/sources">
          Elegir fuente <ArrowRight size={15} aria-hidden="true" />
        </Link>
      </section>
    );

  const source =
    inventory.find((item) => item.source_sha256 === selected) ?? inventory[0];
  return (
    <div className={styles.columns}>
      <section className={`surface-card ${styles.panel}`}>
        <h2 className="text-lg font-semibold">Fuentes registradas</h2>
        <ul className={styles.rows}>
          {inventory.map((item) => (
            <li className={styles.row} key={item.source_sha256}>
              <div>
                <strong>{sourceLabel(item)}</strong>
                <p className="text-sm text-text-secondary">
                  {item.profile ? `Perfil ${item.profile} · ` : ""}
                  {item.zones.length}{" "}
                  {item.zones.length === 1 ? "zona" : "zonas"}
                  {item.revision ? ` · revisión ${item.revision}` : ""}
                </p>
              </div>
              <Button
                variant={source === item ? "primary" : "outline"}
                size="small"
                aria-label={`Consultar zonas de ${sourceLabel(item)}`}
                aria-pressed={source === item}
                onClick={() => setSelected(item.source_sha256)}
              >
                Ver zonas
              </Button>
            </li>
          ))}
        </ul>
      </section>
      <section
        className={`surface-card ${styles.panel}`}
        aria-label="Zonas de la fuente seleccionada"
      >
        <h2 className="text-lg font-semibold">{sourceLabel(source)}</h2>
        <p className="text-sm text-text-secondary">
          {source.updated_at
            ? `Actualizado el ${formatHistoryTime(source.updated_at)}`
            : "Fecha de actualización no disponible"}
        </p>
        {source.zones.length ? (
          <ul className={styles.rows}>
            {source.zones.map((zone) => (
              <li className="py-3" key={zone.zone_id}>
                <strong>{zone.name}</strong>
                <p className="text-sm text-text-secondary">
                  Polígono · {zone.polygon.length} vértices ·{" "}
                  {zone.enabled ? "Activa" : "Inactiva"}
                </p>
                <p className="text-sm text-text-secondary">
                  Identificador para Reglas · {zone.zone_id}
                </p>
                {zone.rules?.length ? (
                  <ul className="mt-2 list-disc pl-5 text-sm">
                    {zone.rules.map((rule) => (
                      <li key={rule.rule_id}>
                        {rule.kind ? ruleTypes[rule.kind] : rule.rule_id} ·{" "}
                        {rule.enabled ? "Activa" : "Inactiva"}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-text-secondary">
                    Sin reglas vinculadas
                  </p>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="py-4">Esta fuente todavía no tiene zonas dibujadas.</p>
        )}
        {source.can_edit && (
          <div className="grid gap-2">
            {!source.session_id && source.source_kind !== "demo" && (
              <p className="text-sm text-text-secondary">
                Vuelve a cargar el archivo original para editar sobre el
                encuadre correcto.
              </p>
            )}
            <Link
              className="button button-primary w-fit"
              href={analysisHref(source)}
            >
              {source.session_id || source.source_kind === "demo"
                ? "Editar con el video"
                : "Cargar video original"}
              <ArrowRight size={15} aria-hidden="true" />
            </Link>
          </div>
        )}
      </section>
    </div>
  );
}
