# Backend/API de Operix

Primera vertical slice de Operix: Django + Django REST Framework recibe un candidato técnico, valida su contrato y conserva un `Event` en PostgreSQL. El replay controlado del Motor ya puede enviar candidatos por HTTP; el pipeline general de video todavía no está integrado de extremo a extremo.

## Requisitos y configuración

- Python 3.12 y las versiones fijadas en `requirements.txt`.
- Una instancia PostgreSQL compatible. En desarrollo puede ser local; la aplicación no depende de cómo se ejecute el servidor.
- Base de datos y usuario de aplicación propios. El usuario local que ejecuta tests necesita `CREATEDB` para la base temporal de Django.

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# Editar .env con credenciales y una DJANGO_SECRET_KEY aleatoria.
set -a; source .env; set +a
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

`.env` está ignorado por Git. `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST` y `POSTGRES_PORT` son obligatorios, igual que `DJANGO_SECRET_KEY`. `DJANGO_DEBUG=1` habilita mensajes de desarrollo; `EVENT_POST_ENABLED=1` habilita expresamente el POST sin autenticación **solo para un entorno controlado**. `DJANGO_ALLOWED_HOSTS` y `CORS_ALLOWED_ORIGINS` son listas separadas por comas. No se permiten todos los orígenes.

## API v1

| Método | Ruta | Resultado |
| --- | --- | --- |
| GET | `/api/v1/health/` | Estado de Django y conexión a PostgreSQL, sin detalles sensibles |
| GET | `/api/v1/events/` | Lista ordenada por `occurred_at` descendente |
| GET | `/api/v1/events/{id}/` | Detalle por UUID |
| POST | `/api/v1/events/` | Crea un evento cuando `EVENT_POST_ENABLED=1` |

La lista admite `event_type`, `occurred_after` y `occurred_before`. Los tiempos requieren zona horaria explícita; ambos límites del período son inclusivos. Los filtros inválidos devuelven 400. No existen PUT, PATCH ni DELETE.

El contrato de POST corresponde al candidato `zone_dwell` implementado actualmente por el Motor, más el contexto civil y de ejecución suministrado por el integrador. Ejemplo exclusivamente sintético:

```json
{
  "analysis_run_id": "12222222-2222-4222-8222-222222222222",
  "view_id": "DEMO-VIEW-01",
  "occurred_at": "2026-10-13T12:00:00Z",
  "video_timestamp_s": "12.400",
  "frame_index": 310,
  "event_type": "zone_dwell",
  "rule_id": "DEMO-R-01",
  "rule_version": 2,
  "rule_parameters": {
    "kind": "zone_dwell",
    "class_name": "person",
    "zone_id": "DEMO-Z-01",
    "min_duration_s": 3.0
  },
  "zone_id": "DEMO-Z-01",
  "track_id": 36,
  "class_name": "person",
  "observed_inside": true,
  "observed_dwell_time_s": "3.400"
}
```

El POST devuelve 201 con esos campos, `id` UUID y `created_at`. El `EventCandidate` del Motor no contiene reloj civil, ID persistente ni ejecución: su adaptador HTTP recibe explícitamente el inicio conocido del medio y un UUID de ejecución, mientras el Backend valida regla/zona/clase/umbral y genera el ID del evento. `rule_id`, `rule_version` y `rule_parameters` quedan congelados como snapshot de trazabilidad. `analysis_run_id` identifica el contexto de la ejecución, pero **todavía no es una clave foránea** porque el modelo de ejecuciones no forma parte de esta slice. Tampoco se almacena evidencia visual binaria ni se clasifica automáticamente Near Miss o riesgo.

## Validación

```bash
set -a; source .env; set +a
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py migrate
.venv/bin/python manage.py test apps.events
```

Las pruebas usan PostgreSQL y crean/destruyen `test_<POSTGRES_DB>`. El Admin registra `Event` solo para inspección: no permite crear, modificar ni borrar eventos desde la interfaz. No hay autenticación ni control de acceso empresarial; no exponer el POST fuera de un entorno de desarrollo controlado.
