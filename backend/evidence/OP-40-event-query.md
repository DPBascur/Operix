# OP-40 — Avance parcial: consulta de eventos

## Objetivo y alcance

Comprobar recuperación y filtros de la API v1 con eventos persistidos en PostgreSQL. Esta evidencia es un **avance parcial de OP-40**: no declara completa la experiencia de consulta ni los criterios funcionales de interfaz.

## Contrato y prueba

`GET /api/v1/events/` devuelve eventos ordenados por `occurred_at` descendente. Los parámetros `event_type`, `occurred_after` y `occurred_before` permiten seleccionar tipo y período con límites inclusivos; los tiempos exigen zona horaria explícita. `GET /api/v1/events/{id}/` recupera un evento por UUID.

Las pruebas automatizadas del Backend cubren listado, orden, detalle, filtros válidos y rechazo de filtros inválidos. En la prueba local de integración, el `EventCandidate` generado por `RuleEngine` a partir de tracks sintéticos se publicó con POST 201 y quedó almacenado con ID `944f3542-6f2f-41f8-a6d5-0dc6d7af00e2`. Un GET de detalle recuperó regla `restricted_zone_presence` v1, frame 4, zona `zona_critica_01`, track temporal 731 y parámetros de la regla. Un GET filtrado con `event_type=zone_dwell`, `occurred_after=2026-10-13T12:00:02Z` y `occurred_before=2026-10-13T12:00:02Z` devolvió solo ese registro. La consulta SQL directa confirmó la misma fila.

El `ApiAdapter` del frontend consultó la lista por HTTP 200; `/events` mostró el evento del Motor junto a los dos eventos DEMO manuales, diferenciables por regla y track. El frontend no se modificó en esta iteración.

## Limitaciones

La vista `/events` conserva búsqueda textual y filtro local por zona; todavía no expone controles de período y tipo conectados a los filtros de la API. No hay paginación, autenticación ni pruebas de volumen histórico. El evento procede de un fixture sintético de tracks y no acredita percepción sobre video real. OP-40 continúa parcial.
