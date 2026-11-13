import type { OperixUser } from "@/services/browser-session";

export type GuideKind = "overview" | "analysis";
export type GuideStep = {
  route: string;
  target: string;
  title: string;
  description: string;
  optional?: string;
  matchPrefix?: boolean;
};

const sources: GuideStep = {
  route: "/sources",
  target: ".source-catalog",
  title: "Selecciona una fuente",
  description:
    "Abre una demo o elige un archivo propio. Puedes usar los controles de esta página y retomar la guía desde el panel.",
};
const analysis: GuideStep = {
  route: "/analysis",
  target: ".analysis-contextbar",
  title: "Comprueba el escenario",
  description:
    "Confirma que el video y el perfil coincidan con el escenario que quieres revisar. El perfil determina la demo y su configuración inicial.",
};
const events: GuideStep = {
  route: "/events",
  target: ".event-ledger",
  title: "Revisa los eventos",
  description:
    "Consulta los registros y usa los filtros para acotar la revisión. Abre un evento disponible para continuar en su dossier.",
};
const evidence: GuideStep = {
  route: "/events",
  matchPrefix: true,
  target: "#evidence-title",
  title: "Abre la evidencia",
  description:
    "El dossier reúne PNG, clip cuando existe, regla y contexto. Un evento indica una condición configurada satisfecha y requiere revisión humana.",
  optional:
    "Abre un evento del historial para ver su evidencia. Si todavía no hay registros, puedes terminar la guía.",
};

const calibration: GuideStep = {
  route: "/analysis",
  target: '[data-guide="calibration"]',
  title: "Decide si necesitas calibración",
  description:
    "Las medidas en metros requieren una cámara fija y referencias físicas conocidas. Un encuadre inválido suspende las medidas dependientes de esa geometría.",
  optional:
    "Abre Zonas, calibración y reglas para localizar Calibración del suelo.",
};

export function guideSteps(
  kind: GuideKind,
  role: OperixUser["role"],
): GuideStep[] {
  const operational = role !== "operator";
  if (kind === "overview") {
    return [
      ...(operational
        ? [
            {
              route: "/",
              target: "main h2",
              title: "Resumen de Operix",
              description:
                "Consulta la actividad registrada y abre los indicadores o el historial desde esta vista.",
            },
          ]
        : []),
      sources,
      analysis,
      {
        route: "/zones",
        target: ".zones-guide, #zone-workbench-title",
        title: "Encuentra las zonas",
        description:
          "Las zonas se trazan sobre la fuente que se va a analizar. Desde esta página puedes volver al editor de Análisis.",
      },
      calibration,
      {
        route: "/rules",
        target: "main h2",
        title: "Consulta las reglas",
        description:
          "Revisa qué reglas están habilitadas por perfil. Para cambiar la configuración de una fuente, usa el editor de Análisis.",
      },
      ...(operational
        ? [
            events,
            evidence,
            {
              route: "/indicators",
              target: "main h2",
              title: "Consulta indicadores",
              description:
                "Compara la evolución y recurrencia de los eventos registrados por período y procedencia.",
            },
          ]
        : []),
      {
        route: "/account",
        target: "main h1",
        title: "Cuenta y seguridad",
        description:
          "Puedes cambiar tu contraseña desde Mi cuenta. Usa el menú de tu cuenta para volver al trabajo o cerrar sesión.",
      },
    ];
  }

  return [
    sources,
    analysis,
    {
      route: "/analysis",
      target: '[aria-label="Configuración espacial"] > button',
      title: "Delimita una zona",
      description:
        "Abre Zonas, calibración y reglas. Traza un polígono sobre el suelo de la fuente actual y revisa sus vértices.",
      optional: "Prepara una demo o un video para habilitar el editor.",
    },
    calibration,
    {
      route: "/analysis",
      target: '[data-guide="rules"]',
      title: "Prepara una regla",
      description:
        "La proximidad puede depender de distancia y duración. El movimiento confirmado exige observaciones suficientes. El ingreso observado requiere una transición desde fuera de la zona.",
      optional: "Abre Zonas, calibración y reglas para localizar Reglas.",
    },
    {
      route: "/analysis",
      target: "#analysis-inspector-trigger",
      title: "Revisa la configuración efectiva",
      description:
        "Abre Detalles y comprueba qué zona, regla y parámetros se utilizarán en la próxima ejecución.",
    },
    {
      route: "/analysis",
      target: '[data-guide="start"]',
      title: "Inicia el análisis cuando estés listo",
      description:
        "Pulsa Iniciar análisis si quieres procesar el video. La guía deja esa decisión en tus manos.",
      optional:
        "Prepara una fuente y aplica la configuración necesaria para habilitar la acción.",
    },
    {
      route: "/analysis",
      target: ".analysis-summary",
      title: "Interpreta el progreso",
      description:
        "El panel muestra fotogramas procesados y FPS del Motor. El resultado final se habilita cuando termina el procesamiento.",
      optional: "Las métricas aparecen cuando hay una sesión de análisis.",
    },
    ...(operational ? [events, evidence] : []),
  ];
}
