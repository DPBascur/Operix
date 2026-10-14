# OP-40 — Consulta de eventos por período y tipo

## Objetivo y alcance

Comprobar recuperación y filtros de la API v1 con eventos persistidos en PostgreSQL y conectarlos a `/events`. El criterio vigente de Backlog V0.11 es: «Los filtros por período y tipo devuelven el conjunto esperado en una prueba con datos conocidos». La evidencia esperada es «Prueba de consulta y resultado esperado/obtenido». Las dependencias son OP-31 y OP-39; RF-07 exige consulta por período y tipo.

## Contrato y prueba

`GET /api/v1/events/` devuelve eventos ordenados por `occurred_at` descendente. Los parámetros `event_type`, `occurred_after` y `occurred_before` permiten seleccionar tipo y período con límites inclusivos; los tiempos exigen zona horaria explícita. `GET /api/v1/events/{id}/` recupera un evento por UUID.

Las pruebas automatizadas del Backend cubren listado, orden, detalle, filtros válidos y rechazo de filtros inválidos. En la prueba local de integración, el `EventCandidate` generado por `RuleEngine` a partir de tracks sintéticos se publicó con POST 201 y quedó almacenado con ID `944f3542-6f2f-41f8-a6d5-0dc6d7af00e2`. Un GET de detalle recuperó regla `restricted_zone_presence` v1, frame 4, zona `zona_critica_01`, track temporal 731 y parámetros de la regla. Un GET filtrado con `event_type=zone_dwell`, `occurred_after=2026-10-13T12:00:02Z` y `occurred_before=2026-10-13T12:00:02Z` devolvió solo ese registro. La consulta SQL directa confirmó la misma fila.

El `ApiAdapter` del frontend consultó la lista por HTTP 200; `/events` mostró el evento del Motor junto a los dos eventos DEMO manuales, diferenciables por regla y track. El frontend no se modificó en esta iteración.

## Limitaciones

En el estado actual, `event_type` representa el tipo técnico persistido: solo se admite `zone_dwell`. No equivale a `rule_id` ni a una categoría de riesgo. Los datos históricos de esta sección proceden de un fixture sintético de tracks y no acreditan percepción sobre video real.

## Consulta conectada a `/events`

`ApiAdapter` envía `event_type`, `occurred_after` y `occurred_before` mediante `URLSearchParams`. Django aplica los filtros sobre PostgreSQL; la vista no filtra estos criterios en memoria. En modo API se muestran controles para hora local desde/hasta y tipo, con acciones explícitas para aplicar y limpiar. El navegador convierte la hora local elegida a ISO 8601 UTC (`Z`); se rechazan fechas inválidas y rangos invertidos. Los límites del Backend son inclusivos. El modo mock conserva el mismo contrato de servicio con datos de ejemplo, sin confundirse con resultados persistidos.

Se consultaron los **12 eventos locales existentes**, sin borrar ni insertar registros para esta prueba. Las horas siguientes se expresan en UTC y son anclas de análisis usadas en la demostración, no fechas acreditadas de captura:

| Consulta `GET /api/v1/events/` | Esperado | Obtenido |
| --- | ---: | ---: |
| Sin parámetros | 12 | 12 |
| `?occurred_after=2026-10-14T17%3A00%3A00Z` | 4 | 4 |
| `?occurred_before=2026-10-14T13%3A44%3A00Z` | 4 | 4 |
| `?occurred_after=2026-10-14T13%3A44%3A00Z&occurred_before=2026-10-14T13%3A45%3A00Z` | 4 | 4 |
| `?event_type=zone_dwell` | 12 | 12 |
| Rango anterior + `event_type=zone_dwell` | 4 | 4 |
| `?occurred_after=2026-10-15T00%3A00%3A00Z` | 0 | 0 |

Los cuatro resultados del rango 13:44–13:45Z son los eventos con IDs `f9749a9f-fbec-4c89-8f24-729d2e263b56`, `f40a62c2-51c5-46ab-9d18-e8da824df274`, `1b442c81-990c-49f9-a74c-0e93f472750d` y `9f1f29db-5970-4a40-9b61-dc0c4a4a7d90`. En `/events`, el rango local 14:00–14:01 mostró cuatro eventos; 10:44–10:45 con tipo `zone_dwell` mostró cuatro; un rango sin coincidencias mostró el estado vacío, y limpiar filtros restauró 12. El rango invertido mostró validación visible. Se revisaron modo claro/oscuro y anchos de 390, 768 y 1280 px.

La suite del Backend agrega pruebas con registros conocidos para listado sin filtro, límites inclusivos, desde, hasta, rango, tipo, combinación, zona horaria explícita, rango invertido y resultado vacío. No se agregaron entidades ni migraciones.

## Estado y límites

La consulta conectada está implementada para el contrato vigente. **OP-40 continúa parcial para su cierre formal**: los 12 registros locales pertenecen al único tipo admitido (`zone_dwell`), por lo que esta muestra no puede demostrar discriminación entre dos tipos válidos. Incorporar un segundo tipo solo para esta prueba alteraría el dominio y queda fuera de alcance. Tampoco se ejecutó una prueba de volumen, autenticación o paginación avanzada. Los estados de error y reintento conservan la ruta de interfaz existente; no se provocó una caída del servicio compartido para probarlos en navegador.
