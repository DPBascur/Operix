# OP-39 — Avance parcial: persistencia de eventos técnicos

## Objetivo

Comprobar una vertical slice técnica que registra eventos mediante una API versionada, los persiste en PostgreSQL y los consulta desde `/events`. La primera prueba usó dos POST manuales DEMO; la segunda añadió un `EventCandidate` producido por la regla real del Motor a partir de tracks sintéticos controlados. Esta evidencia documenta un **avance parcial de OP-39**, no el cumplimiento completo de su criterio de aceptación. Ningún evento representa una operación empresarial real.

## Arquitectura y entorno

El flujo probado ahora es `RuleEngine → EventCandidate → adaptador HTTP del Motor → Django REST Framework /api/v1/events/ → PostgreSQL → Next.js /events`. El `EventCandidate` sigue siendo transitorio. Django valida y guarda una entidad `Event` diferente; ni el Motor accede a PostgreSQL ni el frontend conecta directamente con el Motor.

La comprobación local utilizó PostgreSQL 17.10 como servicio de desarrollo, base `operix_dev` y usuario de aplicación `operix_app`. Django 5.2.18 y DRF 3.18.3 se ejecutaron con Python 3.12. La configuración de conexión, CORS y habilitación de POST provino de variables de entorno; las credenciales no forman parte del repositorio.

## Contrato inicial

`POST /api/v1/events/` admite por ahora `event_type=zone_dwell`. Conserva `analysis_run_id` y `view_id` como contexto provisional de ejecución; `occurred_at` con zona horaria, `video_timestamp_s` y `frame_index`; `rule_id`, `rule_version` y `rule_parameters` como snapshot; `zone_id`, `track_id`, `class_name`, `observed_inside` y `observed_dwell_time_s`. El Backend asigna `id` UUID y `created_at`. Valida campos obligatorios, tipos, zona horaria, claves de parámetros y coherencia de clase, zona y umbral. El contrato JSON completo y un ejemplo sintético están en [README](../README.md).

`GET /api/v1/events/` devuelve la lista más reciente primero y admite filtros `event_type`, `occurred_after` y `occurred_before`; `GET /api/v1/events/{id}/` devuelve un detalle. La consulta y los filtros son un **avance técnico parcial de OP-40**. `GET /api/v1/health/` verifica conexión a la base sin exponer credenciales. No se admiten edición ni eliminación. POST requiere `EVENT_POST_ENABLED=1` en un entorno controlado.

## Pruebas y resultados

- `manage.py check`: sin incidencias.
- `manage.py makemigrations --check --dry-run`: sin cambios pendientes.
- `manage.py migrate`: migración `events.0001_initial` aplicada en PostgreSQL.
- `manage.py test apps.events`: 13/13 pruebas aprobadas usando una base temporal PostgreSQL. Cubren health, creación válida e inválida, persistencia, orden, detalle, filtros, trazabilidad, CORS, prohibición de modificación y POST deshabilitado.
- `GET /api/v1/health/`: HTTP 200, `status=ok`, `database=ok`.
- Dos POST sintéticos: HTTP 201; ambos aparecen en GET lista y detalle. Una consulta SQL directa confirmó las filas en `operix_dev`. Tras reiniciar Django, los mismos UUID siguieron disponibles por GET, lo que confirma persistencia fuera del proceso web.
- Frontend en modo `NEXT_PUBLIC_DATA_SOURCE=api`: la ruta `/events` realizó GET real, mostró las dos filas DEMO manuales —incluyendo regla y track de prueba— y no mostró filas mock. Se comprobaron asimismo estados vacío, error HTTP 503 y recuperación con «Reintentar».
- `pnpm install --frozen-lockfile`, `pnpm format:check`, `pnpm lint`, `pnpm typecheck` y `pnpm build`: aprobados.

## Integración posterior del Motor con la API

Se reutilizó `op30-zone-rule.json` (`zone_dwell`, `restricted_zone_presence` v1, zona `zona_critica_01`, umbral experimental `2.0 s`) y el fixture de seis frames `engine/tests/fixtures/op39-zone-dwell-tracks.ndjson`, SHA-256 `10e0bbead4df4297db5847567a0d5288750167cd2fa279e816b5c26d8102688d`. El fixture contiene **tracks sintéticos ya observados**, no detecciones ejecutadas por YOLO11/ByteTrack ni video empresarial. `SpatiotemporalAnalyzer` y `RuleEngine` procesaron los seis frames a 2 FPS y generaron **un** `EventCandidate` en el frame 4, tiempo de video `2.0 s`, track temporal `731`, pertenencia verdadera y permanencia `2.0 s`; el frame 5 no produjo duplicado.

La ejecución proporcionó explícitamente `analysis_run_id=0bb15335-d5f4-4f9f-8ba5-cfa5f480a57f` e inicio civil sintético del fixture `2026-10-13T12:00:00Z`. El mapeo envió este contrato, sin fabricar esos campos dentro de la regla:

```json
{
  "analysis_run_id": "0bb15335-d5f4-4f9f-8ba5-cfa5f480a57f",
  "view_id": "ceiling_04",
  "occurred_at": "2026-10-13T12:00:02+00:00",
  "video_timestamp_s": "2.000",
  "frame_index": 4,
  "event_type": "zone_dwell",
  "rule_id": "restricted_zone_presence",
  "rule_version": 1,
  "rule_parameters": {
    "kind": "zone_dwell",
    "class_name": "person",
    "zone_id": "zona_critica_01",
    "min_duration_s": 2.0
  },
  "zone_id": "zona_critica_01",
  "track_id": 731,
  "class_name": "person",
  "observed_inside": true,
  "observed_dwell_time_s": "2.000"
}
```

`POST /api/v1/events/` respondió **201**, ID `944f3542-6f2f-41f8-a6d5-0dc6d7af00e2`. `GET /api/v1/events/{id}/` devolvió el mismo contexto y trazabilidad; una consulta SQL directa a PostgreSQL confirmó la fila. El filtro GET por tipo y período exacto devolvió ese evento. En navegador, `/events` consultó la API (200) y mostró tres filas: la regla `restricted_zone_presence` v1 y track `731` del Motor, separados de dos filas manuales `DEMO-R-01` v2.

El nuevo módulo de publicación y el replay aprobaron 11/11 pruebas sin red externa (mapeo, trazabilidad, noop, éxito, repetición en sesión, error HTTP, API no disponible, timeout, respuesta inválida, modo aislado y continuidad tras fallo). La suite completa del Motor aprobó **139 tests ejecutados: 137 pasados, 2 omitidos y 0 fallidos** en el entorno local; los omitidos requieren recursos opcionales externos. `pip check` no encontró requisitos rotos. Django `check`, comprobación de migraciones y 13/13 pruebas backend siguieron aprobando; el frontend sin cambios aprobó `pnpm typecheck` y `pnpm build`.

## Limitaciones

OP-39 permanece incompleto: en esta primera integración sin captura todavía faltaba evidencia visual recuperable y el orquestador general de video no unía detección, tracking, variables, regla y publicación en una sola pasada. Este replay comienza con tracks controlados. `analysis_run_id` es un UUID contextual, sin relación foránea hasta modelar ejecuciones; tampoco existe una tabla de versiones de regla. No se guarda video ni clasificación preventiva. La API solo acepta la regla `zone_dwell` actual. El sink no reintenta y solo evita repetir el mismo intento dentro de su sesión; un timeout ambiguo o una nueva ejecución todavía pueden duplicar el evento en PostgreSQL. POST no tiene autenticación ni autorización empresarial y debe permanecer deshabilitado fuera de desarrollo controlado. Solo `/events` consume la API; las demás vistas conservan mocks. Esta prueba no demuestra rendimiento, volumen histórico ni idoneidad para producción.

## Captura técnica recuperable del frame sintético

La definición vigente de OP-39 en Backlog V0.11 exige ID, fecha/hora, objetos,
zona, regla/versión, parámetros y evidencia recuperable. Se comprobó que los
clips sintéticos existentes no corresponden temporal ni espacialmente al
fixture de tracks de esta prueba. Para no atribuirle una imagen ajena, el Motor
generó una **visualización técnica del estado exacto del frame 4**: zona
configurada, caja del track temporal 731 y rótulo `SINTETICO`, a 2 FPS y
`video_timestamp_s=2.000`. No es un fotograma de cámara ni prueba la detección
o el seguimiento sobre video real.

Ejecución local controlada: `analysis_run_id=43c24711-1051-4a88-a3ac-f616e2db5843`,
inicio sintético `2026-10-13T12:00:00Z`, candidato `zone_dwell` en frame 4.
El POST JSON creó `Event.id=69542b6c-a22b-4212-b873-192ea22bf1bd` (201).
Luego el Motor envió PNG multipart con frame 4 y `2.000 s` al endpoint de
evidencia (201). PostgreSQL contiene la referencia lógica bajo
`events/{event_id}/`; el archivo reside en `OPERIX_MEDIA_ROOT` fuera de Git.
`GET /api/v1/events/{id}/` y la lista devolvieron
`evidence_url=/api/v1/events/{id}/evidence/`; el GET de imagen respondió 200,
`image/png`, 13 619 bytes, SHA-256
`071a1cc67fbf886d9282cabc1001508228d9026f25b57bcb99c2d21ffc767442`.
En `/events` (modo API), la fila `restricted_zone_presence · v1` / track 731
mostró «Ver evidencia» y el enlace abrió el PNG en el navegador. Los eventos
anteriores sin archivo mostraron «Sin evidencia». Esta demostración añadió
captura recuperable al replay, sin cambiar el origen sintético de los datos.

La migración `0002_event_evidence_image` admite `NULL`, por lo que los eventos
anteriores siguen válidos. La suite Motor pasó 141 pruebas y omitió 2; el
Backend pasó sus pruebas de evento y evidencia sobre PostgreSQL. El frontend
pasó formato, ESLint, TypeScript y build. OP-39 **permanece parcial**: el
orquestador completo video→detección→tracking→regla→captura todavía no está
conectado, ni hay controles de acceso, retención, respaldo coordinado o
idempotencia entre ejecuciones. Este ejemplo no debe presentarse como captura
de una cámara real.
