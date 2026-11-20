"use client";

import { PolicyEditor } from "@/features/operations/policy-editor";
import { PageTitle } from "@/components/layout/page-title";
import Link from "next/link";
import { useEffect, useState } from "react";
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
    <div className="page-wrap operational-page">
      <header className="compact-page-header app-page-heading">
        <div>
          <PageTitle>Reglas operacionales</PageTitle>
          <p className="compact-page-copy">
            Crea plantillas, combínalas en conjuntos y asígnalos a una fuente.
            Consulta en{" "}
            <Link href="/analysis" className="underline">
              Análisis
            </Link>{" "}
            la configuración asociada a cada ejecución.
          </p>
        </div>
      </header>
      <PolicyEditor />
      <h2 className="mt-6 text-lg font-semibold">Reglas por perfil</h2>
      <p className="text-sm text-text-secondary">
        Configuración base cuando no hay un conjunto asignado.
      </p>
      {failed && (
        <p role="alert">No se pudo consultar la configuración del servidor.</p>
      )}
      {!failed && !profiles && <p role="status">Consultando perfiles…</p>}
      {profiles?.length === 0 && <p>No hay perfiles disponibles.</p>}
      <div className="rules-catalog grid gap-4">
        {profiles?.map((profile) => (
          <section className="surface-card grid gap-3 p-4" key={profile.id}>
            <h3 className="font-semibold">
              Perfil {profile.id} · {profile.display_name}
            </h3>
            <RuleConfiguration snapshot={profile.configuration} />
          </section>
        ))}
      </div>
    </div>
  );
}
