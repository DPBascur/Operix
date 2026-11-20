# Backend/API de Operix

Django + Django REST Framework gestiona sesiones web con el worker existente,
recibe candidatos de objeto único o pares y conserva eventos en PostgreSQL con
evidencia PNG. Histórico, filtros y frecuencias consultan esos registros. La
integración E2E está comprobada en entorno controlado; no es operación industrial.
Véanse el [estado técnico](../engine/evidence/ETAPA4-TECHNICAL-AUDIT.md#24-final-v020-release-gate-pass--26-10-2026) y la
[alternativa Docker local](../deployment/docker/README.md); el modo nativo se conserva.

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

`.env` está ignorado por Git. `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST` y `POSTGRES_PORT` son obligatorios, igual que `DJANGO_SECRET_KEY`. `DJANGO_DEBUG=1` habilita mensajes de desarrollo. `DJANGO_ALLOWED_HOSTS` y `CORS_ALLOWED_ORIGINS` son listas separadas por comas.

## Acceso y despliegue

1. Ejecutar `python manage.py migrate` y `python manage.py createsuperuser` con el entorno del Backend. Con Compose, usar `docker compose exec backend python manage.py createsuperuser` después de iniciar los servicios. Elegir una contraseña propia. No hay cuenta inicial incluida.
2. Iniciar sesión como administrador y abrir **Usuarios** para crear cuentas,
   asignar roles, cambiar su estado o restablecer contraseñas. Los superusuarios
   actuales conservan su acceso. El rol Administrador creado desde Operix permite
   gestionar el producto y sus cuentas, sin asignar privilegios de Django Admin.
   Las cuentas de Django con permisos administrativos se mantienen en Django.
3. Configurar el frontend con `NEXT_PUBLIC_DATA_SOURCE=api`, `NEXT_PUBLIC_API_BASE_URL=/api/v1` y `OPERIX_API_PROXY_TARGET` apuntando al Backend. Incluir el origen exacto del frontend en `CSRF_TRUSTED_ORIGINS`, con esquema y puerto cuando corresponda. Reiniciar Django y reconstruir Next si se usa un build. Docker Compose utiliza la red interna y el script Tailscale configura los orígenes de la demo.
4. Para HTTPS, configurar `OPERIX_SECURE_COOKIES=1` y el origen HTTPS exacto. Conservar HTTP solo para desarrollo y demo privada controlada. Mantener `DJANGO_SECRET_KEY` estable y privada, y servir evidencias únicamente por la API.

| Rol | Permisos |
| --- | --- |
| Administrador | Gestionar cuentas desde Operix, ejecutar y consultar análisis, configurar zonas y reglas, revisar historial, evidencia e indicadores. |
| Responsable de seguridad | Preparar, configurar y ejecutar sus propios análisis; consultar historial, indicadores, detalle, PNG y clips del despliegue. |
| Visualizador | Consultar indicadores agregados de cargas manuales, Mi cuenta y ayuda. |

Después de aplicar la migración, **Usuarios** marca las cuentas anteriores del
grupo `Usuario` como pendientes de revisión. Conservan sus contraseñas y pasan a
tener acceso de Visualizador. Reasigna a Responsable de seguridad solo a quienes
deban seguir operando análisis, o confirma Visualizador para cerrar la revisión.

`GET /api/v1/indicators/shared/` ofrece totales y frecuencias agregadas de cargas
manuales en el despliegue, que pueden incluir ensayos. Solo admite filtros de
mes UTC y tipo de evento. Excluye demos, nombres, zonas, identificadores y
evidencias. El piloto RTSP aún no ofrece transmisión en navegador ni gestión
de acceso a cámaras.

Esta política mínima sigue la [verificación de acceso de Etapa 4](../engine/evidence/ETAPA4-AUTH-VERIFICATION.md). Las sesiones del navegador duran ocho horas y se guardan en PostgreSQL. Para conservarlas tras reiniciar Django, mantener la misma base y `DJANGO_SECRET_KEY`. El cierre de sesión invalida la sesión en el servidor. La salud de API/DB permanece pública. El alcance de revisión es el despliegue completo.

El login de la API y el de Django Admin comparten presupuestos en PostgreSQL. Cada ventana de `OPERIX_LOGIN_WINDOW_SECONDS` (300 por defecto) admite hasta ocho intentos por origen y cuenta, 30 por cuenta entre todos los orígenes, 80 por origen y 400 en total. Se cuentan solicitudes de credenciales antes de verificar la contraseña y el 429 incluye `Retry-After`. El bloqueo vence al cambiar de ventana y los intentos rechazados no prolongan el plazo. El contador sobrevive al reinicio. Por defecto se usa la dirección TCP. Configurar `OPERIX_TRUSTED_LOGIN_PROXIES` solo con las IP exactas de proxies que agreguen o reemplacen de forma verificable la última IP de `X-Forwarded-For`, y que sean los únicos con acceso a ese tramo. Sin esa configuración, los visitantes detrás de Next pueden compartir el presupuesto del proxy.

Los contadores almacenan HMAC y eliminan identidades de ventanas vencidas al recibir nuevos intentos. El presupuesto global limita cuántas filas se crean por ventana. Cambiar `DJANGO_SECRET_KEY` o la ventana también cambia los presupuestos efectivos. Una campaña sostenida todavía puede causar denegación de acceso temporal; los límites de red y la respuesta operativa siguen siendo necesarios.

Ejecutar las migraciones antes de servir tráfico. Mantener Django Admin en una interfaz privada o deshabilitarlo con `OPERIX_ADMIN_ENABLED=0` en instancias que no lo necesiten. El formulario de seguridad aplica entre 15 y 256 caracteres a nuevas contraseñas, con los validadores de similitud y contraseñas comunes de Django. Las cuentas existentes pueden seguir iniciando sesión con sus contraseñas actuales. El cambio preserva y rota la sesión actual e invalida las demás al siguiente acceso.

La publicación del Motor sigue usando `OPERIX_EVENT_PUBLISH_TOKEN` con `EVENT_POST_ENABLED=1`. En una sola instancia, el token automático dura lo mismo que el proceso Django. Tras un reinicio, un worker previo o un CLI externo necesita el token vigente para publicar. Para compartirlo entre procesos o mantenerlo entre reinicios, generar una vez con `secrets.token_urlsafe(32)` y configurar el mismo valor privado en las instancias autorizadas. Nunca usar una variable `NEXT_PUBLIC_*`. El registro de análisis temporal sigue en memoria y requiere una sola instancia operativa de análisis. Compartir el token no vuelve distribuido ese registro.

`OPERIX_MEDIA_ROOT` define la carpeta de capturas y queda fuera de Git. Respaldar base y archivos juntos para conservar las referencias. La retención de evidencias sigue siendo manual.

### Clips anotados de evidencia

Los análisis web confirmados pueden generar un MP4 anotado por evento persistido. El PNG se conserva. El extracto usa la cadencia del resultado, tiene un lado máximo de 640 px y se genera sin audio ni inferencia adicional. La ventana se centra en el fotograma del evento, se recorta a los límites de la fuente e incluye el fotograma del evento.

- `OPERIX_CLIPS_ENABLED=1` habilita la generación. `OPERIX_CLIP_WINDOW_SECONDS=5` define el margen por lado, de 1 a 10 segundos.
- El detalle devuelve `evidence_clip` cuando está listo. La URL exige UUID de evento y run y aplica el mismo permiso de revisión que el PNG. Los históricos sin clip mantienen el detalle y su PNG.
- Los límites locales son 12 MiB por clip, 512 MiB de MP4 publicados y 24 eventos candidatos por run. La generación usa un único cupo fuera del Motor. Si el cupo está ocupado, falla el códec o se agota la cuota, el evento y el PNG siguen disponibles. Recargar el detalle para consultar clips que se terminaron de generar.
- Los clips y sus metadatos se respaldan con el resto de `OPERIX_MEDIA_ROOT`. Borrar un evento invalida la ruta y programa la retirada del extracto al confirmar la transacción. Tras un cierre abrupto o un bloqueo de archivo, la limpieza de archivos temporales o huérfanos es manual.

## API v1

| Método | Ruta | Resultado |
| --- | --- | --- |
| GET | `/api/v1/health/` | Estado de Django y conexión a PostgreSQL, sin detalles sensibles |
| GET | `/api/v1/events/` | Lista ordenada por `occurred_at` descendente |
| GET | `/api/v1/events/{id}/` | Detalle por UUID |
| POST | `/api/v1/events/` | Crea un evento (201) o devuelve el existente en un retry (200) con publicación habilitada y token válido |
| POST | `/api/v1/events/{id}/evidence/` | Adjunta un PNG (201), reutiliza evidencia existente (200) o completa una imagen ausente |
| GET | `/api/v1/events/{id}/evidence/` | Devuelve el PNG asociado, o 404 si falta |

La lista y las frecuencias admiten `event_type`, `occurred_after`, `occurred_before`, `source_kind` (`demo`, `manual` o `unknown`) y `source_sha256` (huella del video registrada en el evento). Los tiempos requieren zona horaria explícita; ambos límites del período son inclusivos. Los filtros inválidos devuelven 400. No existen PUT, PATCH ni DELETE.

El POST admite `zone_dwell` y `person_forklift_proximity`, más el contexto civil y
de ejecución suministrado por el integrador. El siguiente ejemplo sintético es
de objeto único; el contrato por pares se describe en la sección de publicación:

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

El primer POST devuelve 201 con esos campos, `id` UUID, `created_at` y `created=true`. El `EventCandidate` del Motor no contiene reloj civil, ID persistente ni ejecución: su adaptador HTTP recibe explícitamente el inicio del medio usado en el análisis y un UUID de ejecución, mientras el Backend valida regla/zona/clase/umbral y genera el ID del evento. `rule_id`, `rule_version` y `rule_parameters` quedan congelados como snapshot de trazabilidad. `analysis_run_id` identifica el contexto de la ejecución, pero **todavía no es una clave foránea** porque el modelo de ejecuciones no forma parte de esta slice. No se clasifica automáticamente Near Miss o riesgo.

Para `zone_dwell`, PostgreSQL impone unicidad sobre `(analysis_run_id, view_id, frame_index, rule_id, rule_version, track_id, class_name, zone_id)`. La identidad de pares usa `pair_key` en su propia restricción condicional. Un POST equivalente devuelve el mismo ID con 200 y `created=false`; no crea otra fila. Si esa identidad se reutiliza con datos incompatibles de regla/observación, devuelve 409. El reloj civil suministrado puede variar en un retry: se conserva el `occurred_at` original. El Motor deriva por defecto un `analysis_run_id` estable de los SHA-256 del video, pesos y archivo de configuración, más los parámetros de detector/tracker; no incorpora rutas ni hora actual. Un UUID explícito distinto permite un análisis deliberadamente nuevo. Los registros anteriores no se borran ni reciben una identidad inventada.

La imagen es opcional: primero se crea o recupera el evento y se obtiene su UUID; después se envía `image` (PNG, máximo 2 MiB), `frame_index` y `video_timestamp_s` por multipart al endpoint de evidencia. Los dos valores temporales deben coincidir con el evento. Solo se admite una imagen válida por evento: un POST repetido devuelve 200 sin guardar otro PNG; si la referencia existe pero el archivo falta, un retry puede completarlo. La referencia se guarda en PostgreSQL mediante `FileField`; los bytes quedan en `OPERIX_MEDIA_ROOT`, nunca como blob de base de datos. Lista y detalle exponen `evidence_url` relativo o `null` si no hay archivo disponible; no exponen rutas del filesystem. El GET de imagen devuelve `image/png` y `Cache-Control: no-store`. Un fallo entre ambos POST aún puede dejar temporalmente un evento sin imagen; un retry del Motor puede completarla.

La validación PNG comprueba también descompresión, longitud de scanlines y filtros,
incluido Adam7. Se limita a 4096×4096 y 64 MiB descomprimidos además de los 2 MiB
de archivo: una firma/CRC correctos no bastan para aceptar evidencia ilegible.
Los errores no manejados de PostgreSQL o del almacenamiento se convierten en
HTTP 503 con mensaje genérico, sin SQL, rutas o credenciales. No se reemplazan
los errores de validación 400, conflictos 409 ni ausencia de evidencia 404.

`observed_dwell_time_s` conserva nueve decimales para no perder límites como
1/30 s al transportar duraciones. Acepta los valores históricos de tres decimales;
la respuesta los representa con nueve sin cambiar su valor. La migración 0004
amplía precisión sin inventar datos históricos. La comparación conserva el umbral
original y admite únicamente 1e-9 s de error numérico, como el Motor; no añade
gracia operacional. `video_timestamp_s` mantiene sus tres decimales y los IDs,
fecha civil, configuración, identidad idempotente y reglas no cambian.
Un retry de un evento histórico cuya duración ya se había redondeado puede
devolver 409 si ahora aporta una observación diferente con mayor precisión.
No se sobrescribe el registro antiguo: usar un UUID nuevo únicamente si se
pretende una ejecución nueva, no para ocultar el conflicto de trazabilidad.

## Análisis visual temporal

`/analysis` del Frontend crea una sesión mediante `POST /api/v1/analysis/sessions/`
(multipart con `video` y perfil `A`, `B` o `C`). El Backend guarda el archivo
en un directorio temporal fuera de Git y lanza el Motor con su propio Python.
Configurar `OPERIX_PERSON_WEIGHTS` y `OPERIX_FORKLIFT_WEIGHTS` como rutas
locales a los checkpoints aprobados; `OPERIX_ENGINE_PYTHON` puede indicar el
Python del Motor si difiere de `engine/.venv/Scripts/python.exe`. Los SHA-256
congelados se verifican al iniciar; los pesos no se copian al repositorio.

La API admite `PUT .../{id}/zone/` (perfil y/o vértices normalizados) cuando
no se procesa, `POST .../{id}/start/` para iniciar o reanalizar el mismo video,
`GET .../{id}/status/`, `GET .../{id}/stream/` (MJPEG durante el análisis),
`GET .../{id}/result/` (MP4 H.264 con soporte de rangos),
`POST .../{id}/stop/` para cancelar conservando la fuente, y
`DELETE .../{id}/` para cerrar y borrar la sesión. Al completar se retienen
temporalmente la fuente, el resultado y el snapshot de configuración; el MP4
conserva el FPS de la fuente, distinto del FPS de procesamiento. En Windows el
Motor requiere un codificador H.264 disponible mediante OpenCV/MSMF. No crea
tablas de sesiones nuevas. La publicación opcional de eventos se describe abajo.
Máximo dos sesiones temporales y 250 MiB por archivo por defecto; ajustar
`OPERIX_ANALYSIS_MAX_SESSIONS`, `OPERIX_ANALYSIS_MAX_UPLOAD_BYTES` y
`OPERIX_ANALYSIS_RETENTION_SECONDS` si corresponde. Las salidas temporales se
eliminan tras 3600 s de inactividad por defecto; las consultas de una pestaña
abierta renuevan esa actividad. En un proceso de API local solo se admite un
análisis GPU activo: un segundo inicio se rechaza con HTTP 409 sin modificar
sus salidas y puede reintentarse al terminar el primero. No es un bloqueo
distribuido; ejecutar una sola instancia de API para esta demo. El worker tiene
un límite de 1800 s por trabajo, configurable mediante
`OPERIX_ANALYSIS_TIMEOUT_SECONDS`; al superarlo se termina el proceso y se
informa un error reintentable sin publicar el MP4 parcial. Al desconectarse
MJPEG, las consultas de estado permiten terminar el reloj de preview; un
resultado sin consumidor de preview no espera indefinidamente un stream.
El preview puede mostrar menos FPS que la
fuente. Limitar el acceso de la API a una red controlada.

Las sesiones de análisis y el MP4 de resultado temporal dependen del proceso Django. Si se interrumpe, el Motor se detiene al perder el canal con ese proceso. Tras reiniciar, crear una sesión nueva y volver a cargar o seleccionar la fuente. Los eventos ya persistidos y las evidencias confirmadas se conservan si se mantienen PostgreSQL y el volumen de medios. Un clip cuya generación quedó interrumpida puede seguir ausente.

### Políticas y zonas por fuente

El catálogo se guarda por cuenta. Un conjunto referencia plantillas y admite
ajustes por regla. Si hay varias asignaciones activas, se aplica la de mayor
prioridad en este orden: huella SHA-256 del video, demo y perfil. La asignación
puede ajustar el conjunto para ese destino. Sin un conjunto activo, se usan las
reglas de la configuración espacial de la sesión. Las zonas y la calibración
siguen vinculadas a la fuente donde se definieron.

Al iniciar, Operix valida la combinación efectiva de geometría y reglas. El
recibo de la ejecución conserva configuraciones, versiones y SHA-256. Puedes
consultarlo en `GET /api/v1/analysis/run-snapshots/<run-id>/` con la cuenta
propietaria. Las ediciones posteriores generan nuevas versiones. El inventario
de zonas conserva metadatos y revisiones; para editar tras expirar una sesión,
vuelve a seleccionar la demo o carga el video original.

## Validación

### Publicación operacional desde sesiones web

Con `EVENT_POST_ENABLED=1`, el Backend prepara un contexto por ejecución y el
worker publica automáticamente los candidatos de reglas ya habilitadas. No se
activan nuevas reglas por instalar el transporte. `OPERIX_EVENT_API_BASE_URL`
debe apuntar a la API **local** (por defecto `http://127.0.0.1:8000/api/v1`).
No se toma una URL arbitraria desde el navegador ni se amplía autenticación.

Cada inicio explícito crea un run independiente (`uuid5(session_id, run)`).
Los reintentos de publicación conservan ese run, frame, regla y par. Los snapshots
y PNG quedan bajo `MEDIA_ROOT/analysis-events/<run>/`, con **MANUAL_RETENTION**:
eliminar una sesión temporal no elimina eventos ni evidencia persistida. No se
guarda una copia persistente del video de entrada o del resultado completo.

`status.persistence` distingue `disabled`, `pending`, `saved` y `failed`; el estado
de análisis puede ser `completed` aunque la persistencia sea `failed`. El journal
se conserva antes del HTTP; hasta tres intentos por candidato. Se puede reenviar
sin inferencia con `POST .../sessions/<id>/persistence/retry/` mientras exista la
sesión, o mediante el Python del Motor: `python -m operix_engine.event_outbox
<directorio-local-del-run> --api-url <API-local>`. El reenvío usa el snapshot
original; no recalcula reglas ni cambia identidades para evitar un conflicto.

Un crash o cancelación invalida el último estado de guardado hasta su revisión.
Un journal ausente/truncado o un candidato pendiente sin snapshot completo nunca
se confirma como `saved`; las entradas completas todavía pueden reenviarse.
Si falla la codificación PNG, se retiene únicamente el frame candidato derivado
y su hash para regenerar la imagen sin inferencia. Esta recuperación sigue
sujeta a disponibilidad de almacenamiento y revisión manual de datos incompletos.

No se conoce la fecha civil de grabación de un archivo subido. La fecha UTC del
evento usa el inicio del análisis como ancla más tiempo de video, explicitado en
`source.timestamp_basis=ANALYSIS_START_PROXY_NOT_RECORDING_TIME`. **No es una
afirmación sobre cuándo se grabó la escena.** La source registra nombre sin ruta,
SHA del video/configuración/pesos, sesión y número de run. El dashboard ilustrativo
no genera registros; una ejecución de una muestra demo sí se identifica como tal.

`person_forklift_proximity` guarda ambas identidades en `interaction`, métricas en
`observations`, inicio/emisión en `episode`, regla/versión/parámetros y PNG. Las
columnas heredadas de objeto único quedan nulas para pares; los registros
históricos no reciben observaciones inventadas. Una condición satisfecha no
confirma accidente, Near Miss, infracción ni responsabilidad personal.

Los pares nuevos incorporan `observations.proximity_geometry`: versión
`person_equipment_nearest_ground_edges_v1` y extremos normalizados
`person_anchor` / `equipment_target`. Los históricos sin ese snapshot se conservan
sin reinterpretación. La geometría cambió; los valores de umbral conservados no
acreditan equivalencia ni recalibración. Se admite la versión histórica B
`person_bottom_center_to_equipment_ground_edge_v1` sin convertirla. `person_anchor`
conserva su nombre de campo, pero en D identifica el punto elegido del segmento
PERSON, no su centro. Véase la [corrección A/B/C/D](../engine/evidence/ETAPA4-TECHNICAL-AUDIT.md#15-corrección-final-de-segmentos-inferiores--25-10-2026).

### Frecuencias históricas (OP-41)

`GET /api/v1/events/frequencies/` resume eventos persistidos por día **UTC** y
`event_type`. Acepta los filtros inclusivos `occurred_after`, `occurred_before`
y `event_type` de la lista de eventos, con zona horaria explícita. Devuelve
`total`, `by_period`, `by_type`, `timezone=UTC` y `period=day`; no inventa días
sin registros. Los agregados salen de una consulta PostgreSQL agrupada por
día/tipo. Es una consulta de solo lectura: no crea migraciones ni tipos de
evento adicionales. Se admiten `zone_dwell` y `person_forklift_proximity`.

Los conteos pueden incluir registros de desarrollo: no son tasas verificadas de
incidentes ni indicadores de riesgo. El protocolo y las pruebas figuran en
[la evidencia OP-41](evidence/OP-41-event-frequencies.md).

```bash
set -a; source .env; set +a
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py migrate
.venv/bin/python manage.py test --noinput
```

Las pruebas usan PostgreSQL y crean/destruyen `test_<POSTGRES_DB>`. El Admin registra `Event` solo para inspección: no permite crear, modificar ni borrar eventos desde la interfaz. Los POST internos requieren la credencial del publicador y se deben mantener dentro del perímetro de despliegue acordado.

## PERSON operacional posterior a evaluación

La [demo actual](../assets/demo/v0.2.0/README.md) muestra el recorrido real de
análisis, evidencia e histórico con una configuración demostrativa explícita;
no modifica los perfiles por defecto ni los registros operativos.

`OPERIX_PERSON_WEIGHTS` debe apuntar al `yolo11m.pt` local cuyo SHA es
`d5ffc1a674953a08e11a8d21e022781b1b23a19b730afc309290bd9fb5305b95`.
El Backend transmite ese hash exacto al worker; otro checkpoint se rechaza.
`OPERIX_FORKLIFT_WEIGHTS` conserva el specialist v2. Cambiar `.env` requiere
reiniciar Django; no hay descarga automática ni copia de pesos a Git.
El operating point PERSON sigue 640 / 0,10 / NMS 0,70, filtro `person`,
batch 1, FP32 y CUDA:0. El worker no descarga pesos automáticamente.

Los snapshots de resultado y `source.perception` de eventos nuevos registran
model_id, weights_sha256, class_filter, imgsz, confidence y nms_iou de ambos canales.
Los campos de hash anteriores se conservan; metadata histórica sin `perception`
sigue siendo válida y no se reconstruye. No hay migraciones nuevas.
YOLO11m se seleccionó para análisis diferido mediante métricas de desarrollo;
esta selección no constituye validación independiente final. El holdout ya
observado no se reutiliza para validar m. PRE_EVALUATION_PRIMARY_PERSON y
YOLO11N_COCO_PERSON conservan sus identidades y resultados históricos; PERSON v2
sigue diferido. Véase la [decisión y regresión](../engine/evidence/ETAPA4-TECHNICAL-AUDIT.md).

## Integridad de sesiones y tiempo de video

START explícito permite reutilizar `ready`, `completed`, `error` o `cancelled`,
solo si el worker anterior ya terminó. DELETE y expiración cierran irrevocablemente
esa sesión. Conservan su reserva hasta terminar el proceso, antes de retirarla
del registro. Un temporizador anterior no puede expirar un nuevo run. La exclusión
sigue siendo local a una instancia de API, sin cola ni coordinación multiproceso.

Antes de cargar los modelos, el worker web decodifica la fuente para verificar
conteo, dimensiones y cadencia. Un total declarado distinto del decodificado
impide confirmar integridad: no se sustituye silenciosamente por el leído ni se
confunde metadata aproximada con corrupción demostrada. Si no existe total
declarado, la prelectura fija el total y deja una advertencia. La lectura de análisis
debe repetir ese conteo; la salida H.264 también debe decodificarse completa.

La ruta web admite CFR. Consume timestamps relativos `CAP_PROP_POS_MSEC` cuando
son válidos y concordantes con FPS; rechaza cadencia irregular observable. Si el
backend entrega únicamente ceros, usa tiempo nominal `frame_index / fps` bajo
supuesto CFR, registrado como `NOMINAL_FPS_UNVERIFIED_CFR`: **en ese caso no puede
descartar VFR**. `timestamp_source` y `warnings` quedan en status y snapshot del
resultado temporal. No se añade una nueva propiedad a eventos históricos.

`completed`/100 % requiere lectura y salida verificadas y salida exitosa del worker.
Un receipt final mientras el proceso sigue vivo conserva `processing`.
`preparing` comienza con
porcentaje indeterminado; `processing` se limita a 99,9 % hasta finalizar. Error
y cancelación nunca muestran 100 %. El estado público conserva `error`, con causa
`termination_reason` (por ejemplo `TRUNCATED_INPUT`, `DECODE_FAILURE` o
`UNSUPPORTED_VFR`); no se añade otro enum público. La API devuelve 400 para cuerpos
o parámetros inválidos y 416 para Range inválido. Un archivo con cabecera aceptada
pero ilegible falla asincrónicamente en el worker, sin stack trace al cliente.

Los eventos completos ya publicados antes de un fallo conservan su journal y PNG;
un análisis fallido no los borra ni convierte en prueba de que se procesó todo el
video. No existe rollback de eventos por sesión incompleta. Véase la
[regresión y límites](../engine/evidence/ETAPA4-TECHNICAL-AUDIT.md#12-hardening-de-sesiones-y-video--25-10-2026).
