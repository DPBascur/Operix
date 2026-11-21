"use client";

import {
  cameraLabService,
  type LabCamera,
} from "@/services/camera-lab.service";

import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { OperixScanLoader } from "@/components/ui/operix-scan-loader";
import {
  analysisService,
  type AnalysisProfileDefinition,
} from "@/services/analysis.service";
import { operationalError, operationalRequest } from "./operation-request";
import {
  newParameters,
  ruleTypes,
  type PolicyDocument,
  type PolicyEntry,
  type PolicyKind,
  type PolicyParameters,
  type RegisteredSource,
  type RuleOverride,
  type RuleType,
  type TargetType,
} from "./policy-model";
import styles from "./operations.module.css";

const kinds: { id: PolicyKind; label: string; singular: string }[] = [
  { id: "template", label: "Plantillas", singular: "plantilla" },
  { id: "set", label: "Conjuntos", singular: "conjunto" },
  { id: "assignment", label: "Asignaciones", singular: "asignación" },
];

const resources: Record<PolicyKind, string> = {
  template: "rule-templates",
  set: "rule-sets",
  assignment: "rule-assignments",
};

type EntryResponse = PolicyDocument & {
  id: string;
  version: number;
  updated_at: string;
};
type CollectionResponse = { results: EntryResponse[]; can_edit: boolean };

function entryFromResponse(
  kind: PolicyKind,
  { id, version, updated_at, ...document }: EntryResponse,
): PolicyEntry {
  return { id, kind, version, document, updatedAt: updated_at };
}

function defaultDocument(kind: PolicyKind): PolicyDocument {
  const common = { name: "", enabled: true };
  if (kind === "template")
    return { ...common, parameters: newParameters("zone_dwell") };
  if (kind === "set") return { ...common, rules: [] };
  return { ...common, rule_set_id: "", target_type: "profile", target_id: "" };
}

function Parameters({
  value,
  onChange,
}: {
  value: PolicyParameters;
  onChange: (value: PolicyParameters) => void;
}) {
  const proximity = value.kind === "person_forklift_proximity";
  const pair = proximity || value.kind === "zone_coexistence";
  return (
    <>
      <div className={styles.fieldGrid}>
        <label>
          Condición
          <select
            className="input"
            value={value.kind}
            onChange={(event) =>
              onChange(
                newParameters(event.target.value as RuleType, value.zone_id),
              )
            }
          >
            {Object.entries(ruleTypes).map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Identificador de zona
          <input
            className="input"
            required
            maxLength={64}
            value={value.zone_id}
            onChange={(event) =>
              onChange({ ...value, zone_id: event.target.value })
            }
          />
        </label>
      </div>
      {value.kind !== "zone_entry" && (
        <label>
          Duración mínima (segundos)
          <input
            className="input"
            type="number"
            min="0"
            step="any"
            required
            value={
              (pair ? value.minimum_duration_seconds : value.min_duration_s) ??
              ""
            }
            onChange={(event) =>
              onChange({
                ...value,
                [pair ? "minimum_duration_seconds" : "min_duration_s"]:
                  event.target.value === ""
                    ? undefined
                    : Number(event.target.value),
              })
            }
          />
        </label>
      )}
      {!pair && (
        <label>
          Objeto observado
          <select
            className="input"
            value={value.class_name ?? "person"}
            onChange={(event) =>
              onChange({
                ...value,
                class_name: event.target.value as "person" | "forklift",
              })
            }
          >
            <option value="person">Persona</option>
            <option value="forklift">Montacargas</option>
          </select>
        </label>
      )}
      {proximity && (
        <div className={styles.fieldGrid}>
          <label>
            Unidad de distancia
            <select
              className="input"
              value={value.distance_unit ?? "normalized"}
              onChange={(event) =>
                onChange({
                  ...value,
                  distance_unit: event.target.value as "normalized" | "m",
                })
              }
            >
              <option value="normalized">Distancia normalizada</option>
              <option value="m">Metros (requiere calibración)</option>
            </select>
          </label>
          <label>
            Distancia máxima
            <input
              className="input"
              type="number"
              min="0"
              step="any"
              required
              max={value.distance_unit === "m" ? undefined : Math.SQRT2}
              value={value.max_distance ?? ""}
              onChange={(event) =>
                onChange({
                  ...value,
                  max_distance:
                    event.target.value === ""
                      ? undefined
                      : Number(event.target.value),
                })
              }
            />
          </label>
          <label>
            Movimiento
            <select
              className="input"
              value={value.motion_condition ?? "any"}
              onChange={(event) =>
                onChange({
                  ...value,
                  motion_condition: event.target.value as "any" | "moving",
                })
              }
            >
              <option value="any">Independiente del movimiento</option>
              <option value="moving">Solo con movimiento confirmado</option>
            </select>
          </label>
        </div>
      )}
    </>
  );
}

function AssignmentOverrides({
  entries,
  set,
  overrides,
  onChange,
}: {
  entries: PolicyEntry[];
  set?: PolicyEntry;
  overrides: Record<string, RuleOverride>;
  onChange: (overrides: Record<string, RuleOverride>) => void;
}) {
  if (!set?.document.rules?.length) return null;
  function update(templateId: string, patch: RuleOverride) {
    const next = { ...overrides };
    if (
      patch.enabled === undefined &&
      !Object.keys(patch.parameters ?? {}).length
    )
      delete next[templateId];
    else next[templateId] = patch;
    onChange(next);
  }
  return (
    <details>
      <summary>Ajustes para esta fuente</summary>
      {set.document.rules.map(({ template_id, overrides: setOverride }) => {
        const template = entries.find((entry) => entry.id === template_id);
        if (!template?.document.parameters) return null;
        const selected = overrides[template_id] ?? {};
        const parameters = {
          ...template.document.parameters,
          ...setOverride?.parameters,
        };
        const pair =
          parameters.kind === "person_forklift_proximity" ||
          parameters.kind === "zone_coexistence";
        const duration = pair ? "minimum_duration_seconds" : "min_duration_s";
        function updateParameter(
          key: keyof PolicyParameters,
          value: string | number | undefined,
        ) {
          const next = { ...selected.parameters, [key]: value };
          if (value === undefined) delete next[key];
          update(template_id, { ...selected, parameters: next });
        }
        return (
          <fieldset key={template_id} className="grid gap-2 py-2">
            <legend className="font-semibold">{template.document.name}</legend>
            <div className={styles.fieldGrid}>
              <label>
                Habilitación
                <select
                  className="input"
                  value={
                    selected.enabled === undefined
                      ? ""
                      : String(selected.enabled)
                  }
                  onChange={(event) =>
                    update(template_id, {
                      ...selected,
                      enabled:
                        event.target.value === ""
                          ? undefined
                          : event.target.value === "true",
                    })
                  }
                >
                  <option value="">Heredar</option>
                  <option value="true">Habilitada</option>
                  <option value="false">Deshabilitada</option>
                </select>
              </label>
              <label>
                Zona
                <input
                  className="input"
                  maxLength={64}
                  value={selected.parameters?.zone_id ?? ""}
                  placeholder={parameters.zone_id}
                  onChange={(event) =>
                    updateParameter("zone_id", event.target.value || undefined)
                  }
                />
              </label>
              {parameters.kind !== "zone_entry" && (
                <label>
                  Duración mínima (segundos)
                  <input
                    className="input"
                    type="number"
                    step="any"
                    min="0"
                    value={selected.parameters?.[duration] ?? ""}
                    placeholder={String(parameters[duration] ?? "")}
                    onChange={(event) =>
                      updateParameter(
                        duration,
                        event.target.value === ""
                          ? undefined
                          : Number(event.target.value),
                      )
                    }
                  />
                </label>
              )}
              {parameters.kind === "person_forklift_proximity" && (
                <>
                  <label>
                    Distancia máxima (
                    {parameters.distance_unit === "m" ? "m" : "normalizada"})
                    <input
                      className="input"
                      type="number"
                      step="any"
                      min="0"
                      value={selected.parameters?.max_distance ?? ""}
                      placeholder={String(parameters.max_distance)}
                      onChange={(event) =>
                        updateParameter(
                          "max_distance",
                          event.target.value === ""
                            ? undefined
                            : Number(event.target.value),
                        )
                      }
                    />
                  </label>
                  <label>
                    Movimiento
                    <select
                      className="input"
                      value={selected.parameters?.motion_condition ?? ""}
                      onChange={(event) =>
                        updateParameter(
                          "motion_condition",
                          event.target.value || undefined,
                        )
                      }
                    >
                      <option value="">Heredar</option>
                      <option value="any">Independiente</option>
                      <option value="moving">Confirmado</option>
                    </select>
                  </label>
                </>
              )}
            </div>
          </fieldset>
        );
      })}
    </details>
  );
}

function PolicyHistory({ entry }: { entry: PolicyEntry }) {
  const [history, setHistory] = useState<
    | { version: number; created_at: string; name: string; enabled: boolean }[]
    | null
  >(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  async function load() {
    setError("");
    setLoading(true);
    try {
      const data = await operationalRequest<{
        results: NonNullable<typeof history>;
      }>(`${resources[entry.kind]}/${entry.id}/history/`);
      setHistory(data.results);
    } catch (cause) {
      setError(operationalError(cause));
    } finally {
      setLoading(false);
    }
  }
  if (!history)
    return (
      <div className="mt-3">
        <Button variant="outline" loading={loading} onClick={() => void load()}>
          {error ? "Reintentar historial" : "Ver historial de versiones"}
        </Button>
        {error && <p role="alert">{error}</p>}
      </div>
    );
  return (
    <details open className="mt-3">
      <summary>Historial de versiones</summary>
      <ul className={styles.rows}>
        {history.map((revision) => (
          <li className="py-2 text-sm" key={revision.version}>
            <strong>Versión {revision.version}</strong> · {revision.name} ·{" "}
            {revision.enabled ? "Activa" : "Inactiva"}
            <time
              className="block text-text-secondary"
              dateTime={revision.created_at}
            >
              {new Date(revision.created_at).toLocaleString("es-CL", {
                timeZone: "America/Santiago",
              })}
            </time>
          </li>
        ))}
      </ul>
    </details>
  );
}

export function PolicyEditor() {
  const [canEdit, setCanEdit] = useState(false);
  const [entries, setEntries] = useState<PolicyEntry[]>([]);
  const [sources, setSources] = useState<RegisteredSource[]>([]);
  const [cameras, setCameras] = useState<LabCamera[]>([]);
  const [profiles, setProfiles] = useState<AnalysisProfileDefinition[]>([]);
  const [kind, setKind] = useState<PolicyKind>("template");
  const [editing, setEditing] = useState<PolicyEntry | null>(null);
  const [value, setValue] = useState(() => defaultDocument("template"));
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [feedback, setFeedback] = useState<{
    error: boolean;
    message: string;
  } | null>(null);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    cameraLabService
      .list(controller.signal)
      .then((catalog) => {
        if (active) setCameras(catalog.cameras);
      })
      .catch(() => {
        if (active) setCameras([]);
      });
    Promise.all([
      Promise.all(
        kinds.map(({ id }) =>
          operationalRequest<CollectionResponse>(`${resources[id]}/`),
        ),
      ),
      operationalRequest<{ sources: RegisteredSource[] }>("sources/"),
      analysisService.getProfiles(),
    ])
      .then(([catalog, knownSources, knownProfiles]) => {
        if (!active) return;
        setEntries(
          catalog.flatMap((collection, index) =>
            collection.results.map((entry) =>
              entryFromResponse(kinds[index].id, entry),
            ),
          ),
        );
        setCanEdit(catalog.every((collection) => collection.can_edit));
        setSources(knownSources.sources);
        setProfiles(knownProfiles);
      })
      .catch((error) => {
        if (active) setLoadError(operationalError(error));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [attempt]);

  const current = kinds.find((item) => item.id === kind)!;
  const sets = entries.filter((entry) => entry.kind === "set");
  const selectedSet = sets.find((entry) => entry.id === value.rule_set_id);
  const templates = entries.filter((entry) => entry.kind === "template");
  const targets =
    value.target_type === "camera"
      ? cameras.map((camera) => [camera.id, camera.name])
      : value.target_type === "source"
        ? sources.map((source) => [
            source.source_sha256,
            source.filename ?? source.source_sha256.slice(0, 12),
          ])
        : value.target_type === "demo"
          ? profiles.flatMap((profile) =>
              profile.default_demo_video
                ? [
                    [
                      profile.default_demo_video.id,
                      `Demo ${profile.id} · ${profile.display_name}`,
                    ],
                  ]
                : [],
            )
          : profiles.map((profile) => [
              profile.id,
              `Perfil ${profile.id} · ${profile.display_name}`,
            ]);

  function select(next: PolicyKind, entry: PolicyEntry | null = null) {
    setKind(next);
    setEditing(entry);
    setValue(entry?.document ?? defaultDocument(next));
    setFeedback(null);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setFeedback(null);
    try {
      const path = `${resources[kind]}/${editing ? `${editing.id}/` : ""}`;
      const response = await operationalRequest<EntryResponse>(
        path,
        editing ? "PUT" : "POST",
        editing ? { ...value, version: editing.version } : value,
      );
      const saved = entryFromResponse(kind, response);
      setEntries((list) => [
        ...list.filter((item) => item.id !== saved.id),
        saved,
      ]);
      setEditing(saved);
      setValue(saved.document);
      setFeedback({
        error: false,
        message: `Guardado · versión ${saved.version}`,
      });
    } catch (error) {
      setFeedback({ error: true, message: operationalError(error) });
    } finally {
      setBusy(false);
    }
  }

  if (loading)
    return (
      <OperixScanLoader
        variant="panel"
        message="Cargando catálogo de reglas…"
      />
    );
  if (loadError)
    return (
      <div className="surface-card p-4">
        <p role="alert">{loadError}</p>
        <Button
          variant="outline"
          onClick={() => {
            setLoadError("");
            setLoading(true);
            setAttempt((current) => current + 1);
          }}
        >
          Reintentar catálogo
        </Button>
      </div>
    );

  return (
    <section aria-label="Políticas operacionales" className="grid gap-3">
      <nav aria-label="Secciones de reglas" className={styles.navigation}>
        {kinds.map(({ id, label }) => (
          <Button
            key={id}
            variant={kind === id ? "primary" : "outline"}
            aria-pressed={kind === id}
            disabled={busy}
            onClick={() => select(id)}
          >
            {label}
          </Button>
        ))}
      </nav>
      <div className={styles.columns}>
        <section className={`surface-card ${styles.panel}`}>
          <div className={styles.row}>
            <h2 className="text-lg font-semibold">{current.label}</h2>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => select(kind)}
            >
              Crear {current.singular}
            </Button>
          </div>
          {kind === "assignment" && (
            <p className="text-sm text-text-secondary">
              Prioridad de asignación: fuente concreta, demo y perfil. Los
              análisis guardan la configuración efectiva al iniciar.
            </p>
          )}
          <ul className={styles.rows}>
            {entries
              .filter((entry) => entry.kind === kind)
              .map((entry) => (
                <li key={entry.id} className={styles.row}>
                  <div>
                    <strong>{entry.document.name}</strong>
                    <p className="text-sm text-text-secondary">
                      Versión {entry.version} ·{" "}
                      {entry.document.enabled ? "Activa" : "Inactiva"}
                      {entry.document.parameters &&
                        ` · ${ruleTypes[entry.document.parameters.kind]}`}
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="small"
                    disabled={busy}
                    onClick={() => select(kind, entry)}
                  >
                    Editar
                  </Button>
                </li>
              ))}
          </ul>
          {!entries.some((entry) => entry.kind === kind) && (
            <p className="text-sm text-text-secondary">
              Todavía no hay {current.label.toLowerCase()} guardados en tu
              cuenta.
            </p>
          )}
        </section>
        <section className={`surface-card ${styles.panel}`}>
          <h2 className="mb-3 text-lg font-semibold">
            {editing ? "Editar" : "Crear"} {current.singular}
          </h2>
          {!canEdit && (
            <p role="status">Tu cuenta solo puede consultar el catálogo.</p>
          )}
          <form onSubmit={save}>
            <fieldset className={styles.form} disabled={busy || !canEdit}>
              <label>
                Nombre
                <input
                  className="input"
                  required
                  maxLength={120}
                  value={value.name}
                  onChange={(event) =>
                    setValue({ ...value, name: event.target.value })
                  }
                />
              </label>
              <label>
                Estado
                <select
                  className="input"
                  value={String(value.enabled)}
                  onChange={(event) =>
                    setValue({
                      ...value,
                      enabled: event.target.value === "true",
                    })
                  }
                >
                  <option value="true">Activo</option>
                  <option value="false">Inactivo</option>
                </select>
              </label>
              {kind === "template" && value.parameters && (
                <Parameters
                  value={value.parameters}
                  onChange={(parameters) => setValue({ ...value, parameters })}
                />
              )}
              {kind === "set" && (
                <fieldset className={styles.choices}>
                  <legend>Plantillas del conjunto</legend>
                  {!templates.length && (
                    <p>Crea al menos una plantilla para continuar.</p>
                  )}
                  {templates.map((entry) => (
                    <label key={entry.id}>
                      <input
                        type="checkbox"
                        checked={
                          value.rules?.some(
                            (rule) => rule.template_id === entry.id,
                          ) ?? false
                        }
                        onChange={(event) =>
                          setValue({
                            ...value,
                            rules: event.target.checked
                              ? [
                                  ...(value.rules ?? []),
                                  { template_id: entry.id },
                                ]
                              : (value.rules ?? []).filter(
                                  (rule) => rule.template_id !== entry.id,
                                ),
                          })
                        }
                      />
                      {entry.document.name}
                    </label>
                  ))}
                </fieldset>
              )}
              {kind === "assignment" && (
                <>
                  <label>
                    Conjunto de reglas
                    <select
                      className="input"
                      required
                      value={value.rule_set_id}
                      onChange={(event) =>
                        setValue({
                          ...value,
                          rule_set_id: event.target.value,
                          overrides: undefined,
                        })
                      }
                    >
                      <option value="">Selecciona un conjunto</option>
                      {sets.map((entry) => (
                        <option key={entry.id} value={entry.id}>
                          {entry.document.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className={styles.fieldGrid}>
                    <label>
                      Asignar a
                      <select
                        className="input"
                        value={value.target_type}
                        onChange={(event) =>
                          setValue({
                            ...value,
                            target_type: event.target.value as TargetType,
                            target_id: "",
                          })
                        }
                      >
                        <option value="profile">Perfil</option>
                        <option value="demo">Demo</option>
                        <option value="source">Fuente registrada</option>
                        {(cameras.length > 0 ||
                          value.target_type === "camera") && (
                          <option value="camera">Cámara de laboratorio</option>
                        )}
                      </select>
                    </label>
                    <label>
                      Destino
                      <select
                        className="input"
                        required
                        value={value.target_id}
                        onChange={(event) =>
                          setValue({ ...value, target_id: event.target.value })
                        }
                      >
                        <option value="">Selecciona un destino</option>
                        {targets.map(([id, label]) => (
                          <option key={id} value={id}>
                            {label}
                          </option>
                        ))}
                        {value.target_id &&
                          !targets.some(([id]) => id === value.target_id) && (
                            <option value={value.target_id}>
                              Destino guardado · {value.target_id.slice(0, 12)}
                            </option>
                          )}
                      </select>
                    </label>
                  </div>
                  <AssignmentOverrides
                    entries={entries}
                    set={selectedSet}
                    overrides={value.overrides ?? {}}
                    onChange={(overrides) => setValue({ ...value, overrides })}
                  />
                </>
              )}
              <Button
                type="submit"
                loading={busy}
                disabled={kind === "set" && !value.rules?.length}
              >
                Guardar {current.singular}
              </Button>
            </fieldset>
          </form>
          {editing && (
            <PolicyHistory
              key={`${editing.id}-${editing.version}`}
              entry={editing}
            />
          )}
          {feedback && (
            <p
              className="mt-2 text-sm"
              role={feedback.error ? "alert" : "status"}
            >
              {feedback.message}
            </p>
          )}
        </section>
      </div>
    </section>
  );
}
