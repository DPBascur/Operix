import type { HistoryEvent } from "../../features/dashboard/history-model";

/** Fixture ilustrativa determinista; nunca se mezcla con registros de la API. */
export const historyDemo: HistoryEvent[] = Array.from(
  { length: 146 },
  (_, i) => ({
    id: `demo-${i}`,
    occurred_at: new Date(
      Date.UTC(
        2026,
        i < 82 ? 8 : 9,
        1 + ((i * 11 + Math.floor(i / 5)) % 28),
        6 + ((i * 3) % 15),
        (i * 13) % 60,
      ),
    ).toISOString(),
    event_type: "zone_dwell",
    zone_id: [
      "Pasillo de circulación",
      "Área de carga",
      "Acceso a bodega",
      "Cruce principal",
    ][[0, 0, 0, 1, 1, 2, 3][i % 7]],
  }),
);
