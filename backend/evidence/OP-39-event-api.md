# OP-39 — Avance parcial: persistencia de eventos técnicos

## Objetivo

Comprobar una vertical slice técnica que registra eventos de prueba mediante una API versionada, los persiste en PostgreSQL y los consulta desde la vista `/events` del frontend. Esta evidencia documenta un **avance parcial de OP-39**, no el cumplimiento completo de su criterio de aceptación. Los eventos son **DEMO sintéticos**; no proceden del Motor ni de una operación real.

## Arquitectura y entorno

El flujo probado es `Next.js /events → Django REST Framework /api/v1/events/ → PostgreSQL`. El Motor Python permanece independiente y su `EventCandidate` sigue siendo transitorio. Django valida y guarda una entidad `Event` diferente; no hay conexión directa entre el frontend y el Motor.

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
- Frontend en modo `NEXT_PUBLIC_DATA_SOURCE=api`: la ruta `/events` realizó GET real, mostró las dos filas registradas —incluyendo regla y track de prueba— y no mostró filas mock. Se comprobaron asimismo estados vacío, error HTTP 503 y recuperación con «Reintentar».
- `pnpm install --frozen-lockfile`, `pnpm format:check`, `pnpm lint`, `pnpm typecheck` y `pnpm build`: aprobados.

## Limitaciones

OP-39 permanece incompleto: no se conectó el Motor, no se creó un adaptador `EventCandidate → POST` y no se guarda evidencia visual recuperable. `analysis_run_id` es un UUID contextual, sin relación foránea hasta modelar ejecuciones; tampoco existe una tabla de versiones de regla. No se guarda video ni clasificación preventiva. La API solo acepta la regla `zone_dwell` actual. POST no tiene autenticación ni autorización empresarial y debe permanecer deshabilitado fuera de desarrollo controlado. Solo `/events` consume la API; las demás vistas conservan mocks. Esta prueba no demuestra rendimiento, volumen histórico ni idoneidad para producción.
