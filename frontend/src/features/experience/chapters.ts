export const chapters = [
  {
    name: "Observación",
    title: "Todo comienza con una observación.",
    description:
      "Una fuente de video entrega la escena que Operix examina cuadro a cuadro.",
    detail: "Fuente de video",
  },
  {
    name: "Detección",
    title: "La IA identifica los elementos relevantes.",
    description:
      "El detector distingue a la persona y al montacargas. Las cajas marcan dónde aparecen en la imagen.",
    detail: "Persona y montacargas",
  },
  {
    name: "Seguimiento",
    title: "Cada objeto conserva su identidad.",
    description:
      "El seguimiento enlaza observaciones consecutivas. Así, Operix puede interpretar trayectorias y duración.",
    detail: "Trayectorias por objeto",
  },
  {
    name: "Contexto",
    title: "La posición adquiere contexto.",
    description:
      "Una zona delimita el suelo que interesa revisar. Operix relaciona posición, proximidad y tiempo. Las mediciones en metros requieren una calibración válida.",
    detail: "Zona operacional",
  },
  {
    name: "Reglas",
    title: "Las reglas definen qué observar.",
    description:
      "En esta simulación, la regla combina proximidad, movimiento confirmado y duración. Operix evalúa los tres requisitos.",
    detail: "Proximidad · Movimiento · Duración",
  },
  {
    name: "Evento",
    title: "Una condición cumplida genera un evento.",
    description:
      "Operix registra el momento y la regla aplicada. El registro requiere revisión humana y por sí solo no confirma un incidente.",
    detail: "Condición configurada satisfecha",
  },
  {
    name: "Evidencia",
    title: "La evidencia queda disponible para revisión humana.",
    description:
      "El dossier reúne el fotograma PNG, el clip cuando está disponible y el contexto de la regla. Se puede volver al registro desde el historial.",
    detail: "Fotograma · Clip · Historial",
  },
] as const;
