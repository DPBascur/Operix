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
  target:
    '.source-card a[href*="profile="], .source-card a[href*="source=manual"]',
  title: "Selecciona una fuente",
  description:
    "Abre una demo o elige un archivo propio. Puedes usar los controles de esta página y retomar la guía desde el panel.",
};
const analysis: GuideStep = {
  route: "/analysis",
  target:
    ".analysis-context-button:has(input[type=file]:enabled), .analysis-profile[aria-pressed=true]",
  title: "Comprueba el escenario",
  description:
    "Confirma que el video y el perfil coincidan con el escenario que quieres revisar. El perfil determina la demo y su configuración inicial.",
};
const events: GuideStep = {
  route: "/events",
  target: ".event-ledger select",
  title: "Revisa los eventos",
  description:
    "Consulta los registros y usa los filtros para acotar la revisión. Abre un evento disponible para continuar en su dossier.",
};
const evidence: GuideStep = {
  route: "/events",
  matchPrefix: true,
  target:
    'figure[aria-labelledby="evidence-title"] a, figure[aria-labelledby="evidence-title"] video, .event-ledger a[href^="/events/"]',
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
  if (role === "viewer") {
    return [
      {
        route: "/indicators",
        target: "#shared-indicator-month",
        title: "Consulta indicadores",
        description:
          "Elige un mes para ver el total y la distribución de los eventos compartidos.",
      },
      {
        route: "/account",
        target: "#current",
        title: "Cuenta y seguridad",
        description: "Consulta tu rol o cambia tu contraseña.",
      },
    ];
  }
  if (kind === "overview") {
    return [
      {
        route: "/",
        target: 'main a[href^="/indicators"]',
        title: "Resumen de Operix",
        description:
          "Consulta la actividad registrada y abre los indicadores o el historial desde esta vista.",
      },
      sources,
      analysis,
      {
        route: "/zones",
        target: 'main a[href="/analysis"]',
        title: "Encuentra las zonas",
        description:
          "Las zonas se trazan sobre la fuente que se va a analizar. Desde esta página puedes volver al editor de Análisis.",
      },
      calibration,
      {
        route: "/rules",
        target: 'main a[href="/analysis"]',
        title: "Consulta las reglas",
        description:
          "Revisa qué reglas están habilitadas por perfil. Para cambiar la configuración de una fuente, usa el editor de Análisis.",
      },
      events,
      evidence,
      {
        route: "/indicators",
        target: ".history-controls select",
        title: "Consulta indicadores",
        description:
          "Compara la evolución y recurrencia de los eventos registrados por período y procedencia.",
      },
      {
        route: "/account",
        target: "#current",
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
      target:
        '[aria-label="Zona seleccionada"], [aria-label="Configuración espacial"] > button',
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
        "Si la fuente expiró, elige otra demo o un archivo. Si el editor está abierto, revisa los cambios y ciérralo antes de iniciar.",
    },
    {
      route: "/analysis",
      target: "#analysis-inspector-trigger",
      title: "Interpreta el progreso",
      description:
        "El panel muestra fotogramas procesados y FPS del Motor. El resultado final se habilita cuando termina el procesamiento.",
      optional: "Las métricas aparecen cuando hay una sesión de análisis.",
    },
    events,
    evidence,
  ];
}
