"use client";

import { Plus, ShieldAlert, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { AppShell } from "@/components/layout/app-shell";
import { MockDataNotice } from "@/components/ui/mock-data-notice";
import { PageHeader } from "@/components/ui/page-header";
import { Toggle } from "@/components/ui/toggle";
import { StatusBadge } from "@/components/ui/status-badge";
import { mockRuleRows } from "@/mocks/ui-data";

export default function RulesPage() {
  const [enabledRuleIds, setEnabledRuleIds] = useState<string[]>(() =>
    mockRuleRows.filter((rule) => rule.enabled).map((rule) => rule.id),
  );
  return (
    <AppShell activePath="/rules">
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 sm:py-8 lg:px-8 lg:py-10">
        <PageHeader
          action={
            <Button disabled title="Disponible con la futura API">
              <Plus aria-hidden="true" size={17} />
              Nueva regla
            </Button>
          }
          description="Revisa la presentación de reglas configurables antes de integrar la API."
          eyebrow="Configuración"
          title="Reglas operacionales"
        />
        <MockDataNotice />
        <section aria-label="Reglas simuladas" className="space-y-3">
          {mockRuleRows.map(({ id, title, description, zone, tone }) => (
            <article
              className="surface-card flex flex-col gap-4 rounded-card border border-border bg-surface-elevated p-5 shadow-card sm:flex-row sm:items-center sm:p-6"
              key={id}
            >
              <span className="flex size-11 shrink-0 items-center justify-center rounded-control bg-brand-accent/10 text-accent">
                <ShieldAlert aria-hidden="true" size={21} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-3">
                  <StatusBadge tone={tone}>{id}</StatusBadge>
                  <h2 className="font-semibold text-foreground">{title}</h2>
                </div>
                <p className="mt-2 text-sm leading-6 text-text-secondary">
                  {description}
                </p>
                <p className="mt-2 text-xs font-medium text-text-secondary">
                  Zona asociada: {zone}
                </p>
                <details className="rule-details mt-2">
                  <summary className="cursor-pointer py-2 text-xs font-medium text-primary">
                    Condiciones y parámetros
                  </summary>
                  <dl className="mt-2 grid gap-2 text-xs">
                    <div>
                      <dt className="font-semibold">Tipo</dt>
                      <dd className="mt-1 text-text-secondary">{title}</dd>
                    </div>
                    <div>
                      <dt className="font-semibold">Condición</dt>
                      <dd className="mt-1 text-text-secondary">
                        {description}
                      </dd>
                    </div>
                    <div>
                      <dt className="font-semibold">Parámetros</dt>
                      <dd className="mt-1 text-text-secondary">
                        Umbrales no definidos en esta demostración.
                      </dd>
                    </div>
                  </dl>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button disabled title="Requiere integración con la API">
                      Guardar regla
                    </Button>
                    <Button
                      variant="destructive"
                      disabled
                      title="Requiere integración con la API"
                      aria-label={`Eliminar regla ${id}`}
                    >
                      <Trash2 size={15} aria-hidden="true" />
                      Eliminar regla
                    </Button>
                  </div>
                </details>
              </div>
              <div className="flex items-center justify-between gap-4 sm:justify-end">
                <label
                  className={`flex items-center gap-2 text-xs font-medium ${enabledRuleIds.includes(id) ? "text-active" : "text-text-secondary"}`}
                >
                  <Toggle
                    checked={enabledRuleIds.includes(id)}
                    onChange={(event) =>
                      setEnabledRuleIds((current) =>
                        event.target.checked
                          ? [...current, id]
                          : current.filter((currentId) => currentId !== id),
                      )
                    }
                    aria-label={`${id}: ${enabledRuleIds.includes(id) ? "habilitada" : "deshabilitada"} en esta demostración`}
                  />
                  <span>
                    {enabledRuleIds.includes(id)
                      ? "Habilitada"
                      : "Deshabilitada"}
                    {" · Mock"}
                  </span>
                </label>
              </div>
            </article>
          ))}
        </section>
      </div>
    </AppShell>
  );
}
