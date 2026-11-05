"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { RuleConfiguration } from "@/features/analysis/rule-configuration";
import {
  analysisService,
  type AnalysisProfileDefinition,
} from "@/services/analysis.service";

export default function RulesPage() {
  const [profiles, setProfiles] = useState<AnalysisProfileDefinition[] | null>(
    null,
  );
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let current = true;
    analysisService.getProfiles().then(
      (data) => {
        if (current) setProfiles(data);
      },
      () => {
        if (current) setFailed(true);
      },
    );
    return () => {
      current = false;
    };
  }, []);

  return (
    <AppShell activePath="/rules">
      <div className="page-wrap operational-page">
        <header className="compact-page-header">
          <div>
            <h2 className="compact-page-title">Reglas por perfil</h2>
            <p className="compact-page-copy">
              Configuración base del servidor. Consulta en{" "}
              <Link href="/analysis" className="underline">
                Análisis
              </Link>{" "}
              el snapshot asociado a la fuente y ejecución.
            </p>
          </div>
          <span className="source-indicator">Solo lectura</span>
        </header>
        {failed && (
          <p role="alert">
            No se pudo consultar la configuración del servidor.
          </p>
        )}
        {!failed && !profiles && <p role="status">Consultando perfiles…</p>}
        {profiles?.length === 0 && <p>No hay perfiles disponibles.</p>}
        <div className="grid gap-4">
          {profiles?.map((profile) => (
            <section
              className="grid gap-3 rounded-lg border border-border p-4"
              key={profile.id}
            >
              <h3 className="font-semibold">
                Perfil {profile.id} · {profile.display_name}
              </h3>
              <RuleConfiguration snapshot={profile.configuration} />
            </section>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
