"use client";

import { ChevronDown } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { MockDataNotice } from "@/components/ui/mock-data-notice";
import { mockRuleRows } from "@/mocks/ui-data";

export default function RulesPage() {
  return (
    <AppShell activePath="/rules">
      <div className="page-wrap operational-page">
        <header className="compact-page-header">
          <div>
            <h2 className="compact-page-title">Interpretación operacional</h2>
            <p className="compact-page-copy">
              La percepción observa objetos; las reglas interpretan el contexto.
            </p>
          </div>
          <span className="source-indicator">Referencia no persistente</span>
        </header>
        <MockDataNotice />

        <section aria-labelledby="rules-list-title" className="structured-list">
          <div className="structured-list-head" aria-hidden="true">
            <span>Regla</span>
            <span>Zona</span>
            <span>Estado</span>
          </div>
          <h2 id="rules-list-title" className="sr-only">
            Reglas configuradas
          </h2>
          {mockRuleRows.map(({ id, title, description, zone, enabled }) => {
            return (
              <article className="rule-row" key={id}>
                <div className="min-w-0">
                  <div className="flex items-baseline gap-3">
                    <span className="technical-id">{id}</span>
                    <h3 className="text-sm font-semibold">{title}</h3>
                  </div>
                  <p className="mt-1 max-w-2xl text-sm leading-5 text-text-secondary">
                    {description}
                  </p>
                  <details className="rule-details mt-2">
                    <summary className="inline-flex cursor-pointer items-center gap-1 py-1 text-xs font-semibold text-text-secondary hover:text-foreground">
                      Condiciones <ChevronDown size={13} aria-hidden="true" />
                    </summary>
                    <dl className="mt-2 grid gap-2 border-l border-border pl-3 text-xs text-text-secondary">
                      <div>
                        <dt className="inline font-semibold text-foreground">
                          Observa:{" "}
                        </dt>
                        <dd className="inline">{title}</dd>
                      </div>
                      <div>
                        <dt className="inline font-semibold text-foreground">
                          Condición:{" "}
                        </dt>
                        <dd className="inline">{description}</dd>
                      </div>
                    </dl>
                  </details>
                </div>
                <p className="text-xs text-text-secondary">{zone}</p>
                <p className="text-right text-xs text-text-secondary">
                  {enabled ? "Activa en muestra" : "Inactiva en muestra"}
                </p>
              </article>
            );
          })}
        </section>
      </div>
    </AppShell>
  );
}
