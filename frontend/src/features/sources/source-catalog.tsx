"use client";

import {
  ArrowRight,
  Camera,
  Clapperboard,
  FileVideo,
  MonitorUp,
  Play,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  analysisService,
  type AnalysisProfile,
  type AnalysisProfileDefinition,
} from "@/services/analysis.service";
import type { VideoSource } from "@/types/operix";

const fallbackNames: Record<AnalysisProfile, string> = {
  A: "Warehouse fire",
  B: "Forklift / human",
  C: "Box pickup",
};

function SourcePreview({ source }: { source: VideoSource }) {
  if (!source.previewUrl) {
    return (
      <div className="source-preview-fallback" aria-hidden="true">
        {source.type === "local" ? <FileVideo /> : <Clapperboard />}
      </div>
    );
  }
  return (
    <video
      className="source-preview-video"
      muted
      playsInline
      preload="metadata"
      src={source.previewUrl}
      onLoadedMetadata={(event) => {
        event.currentTarget.currentTime = 0.1;
      }}
      aria-label={`Vista previa de ${source.name}`}
    />
  );
}

function SourceCard({
  source,
  profile,
}: {
  source: VideoSource;
  profile?: AnalysisProfile;
}) {
  const href =
    source.type === "local"
      ? "/analysis?source=manual"
      : `/analysis?profile=${profile ?? "A"}`;
  return (
    <article className="source-card">
      <div className="source-card-media">
        <SourcePreview source={source} />
        <span className="source-card-status">
          <span aria-hidden="true" /> Disponible
        </span>
      </div>
      <div className="source-card-body">
        <div>
          <h3>{source.name}</h3>
          <p>{source.location}</p>
        </div>
        <Link href={href} aria-label={`Abrir ${source.name} en análisis`}>
          Abrir <ArrowRight aria-hidden="true" />
        </Link>
      </div>
    </article>
  );
}

export function SourceCatalog({ compact = false }: { compact?: boolean }) {
  const [profiles, setProfiles] = useState<AnalysisProfileDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    analysisService.getProfiles().then(
      (catalog) => {
        if (!active) return;
        setProfiles(catalog);
        setLoading(false);
      },
      () => {
        if (!active) return;
        setError("Las demos no están disponibles en este momento.");
        setLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, []);

  const demoSources = useMemo(
    () =>
      profiles.flatMap((definition) => {
        const demo = definition.default_demo_video;
        if (!demo) return [];
        const source: VideoSource = {
          id: demo.id,
          name: `Demo ${definition.id}`,
          type: "demo",
          status: "available",
          previewUrl: analysisService.getDemoSourceUrl(definition.id, demo.id),
          location: definition.display_name || fallbackNames[definition.id],
        };
        return [{ source, profile: definition.id }];
      }),
    [profiles],
  );

  const localSource: VideoSource = {
    id: "local-video",
    name: "Video local",
    type: "local",
    status: "available",
    location: "Archivo MP4, MOV o AVI",
  };

  return (
    <div className={compact ? "source-catalog is-compact" : "source-catalog"}>
      {compact && (
        <section className="analysis-launch" aria-labelledby="launch-title">
          <div className="analysis-launch-copy">
            <span className="eyebrow">Sesión local</span>
            <h2 id="launch-title">Comenzar un análisis</h2>
            <p>
              Seleccione una demo validada o prepare un video desde este equipo.
            </p>
          </div>
          <div className="analysis-launch-actions">
            {(["A", "B", "C"] as AnalysisProfile[]).map((profile) => (
              <Link key={profile} href={`/analysis?profile=${profile}`}>
                <Play aria-hidden="true" /> Demo {profile}
              </Link>
            ))}
            <Link className="is-primary" href="/analysis?source=manual">
              <MonitorUp aria-hidden="true" /> Video local
            </Link>
          </div>
        </section>
      )}

      <section
        aria-labelledby={compact ? "home-sources-title" : "demo-sources-title"}
      >
        <div className="section-intro">
          <div>
            <span className="eyebrow">Disponibles ahora</span>
            <h2 id={compact ? "home-sources-title" : "demo-sources-title"}>
              {compact ? "Fuentes" : "Demos"}
            </h2>
          </div>
          {compact && (
            <Link href="/sources">
              Ver todas <ArrowRight aria-hidden="true" />
            </Link>
          )}
        </div>
        {loading ? (
          <div
            className="source-grid"
            aria-label="Cargando fuentes"
            aria-busy="true"
            role="status"
          >
            {[0, 1, 2].map((item) => (
              <div className="source-card source-card-loading" key={item} />
            ))}
          </div>
        ) : error ? (
          <p className="inline-message is-error" role="alert">
            {error}
          </p>
        ) : (
          <div className="source-grid">
            {demoSources.map(({ source, profile }) => (
              <SourceCard key={source.id} source={source} profile={profile} />
            ))}
            {!compact && <SourceCard source={localSource} />}
          </div>
        )}
      </section>

      {!compact && (
        <>
          <section
            className="source-section"
            aria-labelledby="local-source-title"
          >
            <div className="section-intro">
              <div>
                <span className="eyebrow">Desde este equipo</span>
                <h2 id="local-source-title">Videos locales</h2>
              </div>
            </div>
            <div className="local-source-row">
              <span className="local-source-icon" aria-hidden="true">
                <MonitorUp />
              </span>
              <div>
                <h3>Seleccionar un archivo de video</h3>
                <p>
                  El archivo se prepara dentro de una sesión temporal de
                  análisis.
                </p>
              </div>
              <Link
                className="button button-primary"
                href="/analysis?source=manual"
              >
                Seleccionar video <ArrowRight aria-hidden="true" />
              </Link>
            </div>
          </section>

          <section
            className="source-section"
            aria-labelledby="camera-source-title"
          >
            <div className="section-intro">
              <div>
                <span className="eyebrow">Próxima capacidad</span>
                <h2 id="camera-source-title">Cámaras</h2>
              </div>
            </div>
            <div className="camera-empty">
              <Camera aria-hidden="true" />
              <div>
                <h3>Aún no hay cámaras configuradas</h3>
                <p>
                  Las futuras fuentes IP aparecerán aquí cuando esa capacidad
                  esté disponible.
                </p>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
