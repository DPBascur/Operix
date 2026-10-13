export const mockCurrentUser = {
  displayName: "Daniel",
  role: "Administrador",
} as const;

export const mockDashboardMetrics = [
  {
    key: "streams",
    label: "Fuentes de video",
    value: "1",
  },
  {
    key: "objects",
    label: "Objetos en escena",
    value: "3",
  },
  {
    key: "events",
    label: "Candidatos de evento",
    value: "2",
  },
  {
    key: "duration",
    label: "Duración simulada",
    value: "24 min",
  },
] as const;

export const mockRecentEvents = [
  {
    id: "mock-event-01",
    title: "Cruce de zona restringida",
    detail: "Zona A · Regla R-01",
    time: "10:24:17",
    status: "Nuevo",
    tone: "accent",
  },
  {
    id: "mock-event-02",
    title: "Permanencia prolongada",
    detail: "Zona B · Regla R-03",
    time: "10:21:03",
    status: "En revisión",
    tone: "cyan",
  },
  {
    id: "mock-event-03",
    title: "Proximidad entre personas",
    detail: "Zona C · Regla R-05",
    time: "10:18:56",
    status: "Sin clasificar",
    tone: "neutral",
  },
  {
    id: "mock-event-04",
    title: "Objeto no autorizado",
    detail: "Zona A · Regla R-02",
    time: "10:15:12",
    status: "Nuevo",
    tone: "accent",
  },
] as const;

export const mockEventRows = [
  {
    id: "mock-row-01",
    title: "Cruce de zona restringida",
    zone: "Zona A",
    rule: "R-01",
    confidence: 0.87,
    time: "10:24:17",
    status: "Nuevo",
    tone: "accent",
  },
  {
    id: "mock-row-02",
    title: "Permanencia prolongada",
    zone: "Zona B",
    rule: "R-03",
    confidence: 0.76,
    time: "10:21:03",
    status: "En revisión",
    tone: "cyan",
  },
  {
    id: "mock-row-03",
    title: "Proximidad entre personas",
    zone: "Zona C",
    rule: "R-05",
    confidence: 0.82,
    time: "10:18:56",
    status: "Sin clasificar",
    tone: "neutral",
  },
  {
    id: "mock-row-04",
    title: "Objeto no autorizado",
    zone: "Zona A",
    rule: "R-02",
    confidence: 0.91,
    time: "10:15:12",
    status: "Nuevo",
    tone: "accent",
  },
  {
    id: "mock-row-05",
    title: "Caída de objeto",
    zone: "Zona D",
    rule: "R-04",
    confidence: 0.68,
    time: "10:12:41",
    status: "En revisión",
    tone: "cyan",
  },
] as const;

export const mockRuleRows = [
  {
    id: "R-01",
    title: "Cruce de zona restringida",
    description: "Detecta entradas no autorizadas en zonas restringidas.",
    zone: "Zona A",
    enabled: true,
    tone: "accent",
  },
  {
    id: "R-02",
    title: "Objeto no autorizado",
    description: "Identifica objetos fuera de las áreas permitidas.",
    zone: "Zona A",
    enabled: true,
    tone: "cyan",
  },
  {
    id: "R-03",
    title: "Permanencia prolongada",
    description: "Alerta cuando un objeto permanece demasiado tiempo.",
    zone: "Zona B",
    enabled: true,
    tone: "cyan",
  },
  {
    id: "R-04",
    title: "Caída de objeto",
    description: "Detecta cambios bruscos de posición en objetos.",
    zone: "Zona D",
    enabled: false,
    tone: "neutral",
  },
  {
    id: "R-05",
    title: "Proximidad entre personas",
    description: "Advierte proximidad entre personas en zonas sensibles.",
    zone: "Zona C",
    enabled: false,
    tone: "neutral",
  },
] as const;
