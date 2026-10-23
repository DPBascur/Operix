# Interfaz de revisión preventiva

## Alcance

La interfaz conserva el Motor y el contrato de análisis. No añade ni modifica modelos, thresholds, geometría, tracking, reglas ni transporte. La navegación agrupa operación (resumen, fuentes, análisis y eventos) y gestión (reglas, zonas, indicadores y usuarios).

## Histórico

`/`, `/dashboard` (redirección) e `/indicators` ofrecen el dashboard. El selector identifica explícitamente dos fuentes:

- **Ejemplo ilustrativo**: fixture determinista centralizada en `src/services/demo/history-demo.ts`, sin representar incidentes de una organización.
- **Registros API**: `GET /api/v1/events/`, validación de respuesta y agregación cliente. Un error no se sustituye por ejemplos. No se incorporó el prototipo de frecuencias de otra rama.

Se calcula por mes UTC: total, comparación contra el mes anterior, ranking de zonas, conteos diarios/horarios, tipos y actividad reciente. Si el mes anterior no tiene registros, no se inventa un porcentaje. Los totales por día, hora, zona y tipo se contrastan con pruebas independientes. La API actual devuelve una lista completa; antes de escalar a históricos grandes se requerirá agregación/paginación en servidor y pruebas de cobertura.

La intención procede de la Sección 6.2 (RF-07/RF-08), Cuadro 6 de trazabilidad y fila RF-08 de la matriz del informe de Etapa 1: consulta de antecedentes y frecuencias verificables para revisar recurrencias. No supone medición de riesgo, reducción causal de incidentes ni validación industrial. Actualmente la API admite `zone_dwell`; no se inventa una segunda categoría operacional.

## Estado de servicios

El indicador global usa `GET /api/v1/health/`, que verifica API y base de datos. Consulta cada 30 segundos, timeout de 5 segundos, suspende consultas con documento oculto y libera requests al desmontar. Distingue conectado, problema HTTP/salud, sin conexión y no configurado. No certifica GPU, pesos o disponibilidad de cámaras.

## Acceso y cuentas demo

`/login` no pide ni guarda contraseñas. Seleccionar una cuenta activa abre una **sesión demostrativa** local. Se puede continuar al análisis sin sesión. No es una frontera de seguridad y no protege rutas ni API.

`/users` permite búsqueda y filtro por rol, crear, editar, desactivar y reactivar cuentas. No hay eliminación destructiva ni invitaciones. La edición visual requiere seleccionar Administrador demo; un jefe o usuario común puede consultar el directorio. Esto no representa RBAC de servidor.

- Cuentas: `localStorage`, clave versionada `operix-demo-users-v1`.
- Sesión: `sessionStorage`, clave `operix-demo-session-v1`.
- Fixtures: nombres de equipo y dominios `example.test`; introducir únicamente información ficticia.
- Rechaza correos duplicados, roles inválidos, datos corruptos y pérdida del último administrador activo.
- El adaptador local está separado en `src/services/demo/`; la integración productiva necesitará endpoints, sesiones seguras, autorización Backend, auditoría y estrategia de recuperación. No existe sincronización multiusuario.

## Interacción y accesibilidad

Botones reutilizables primary/secondary/ghost/outline/destructive, tamaños default/icon/small; controles solo icono requieren nombre accesible. Foco visible, formularios etiquetados, avisos de éxito/error y cancelación. El login incluye un preview analítico animado ilustrativo, no un stream del Motor. Su animación es acotada y respeta `prefers-reduced-motion`.

## Verificación

Con las versiones Node/pnpm fijadas por el proyecto: `pnpm test`, `pnpm lint`, `pnpm typecheck`, `pnpm build`. Las nuevas pruebas no necesitan GPU ni Backend. La comprobación visual incluye las nuevas vistas a 1920, 1366, 768 y 390 píxeles, así como navegación y regresión del análisis existente.

No se cambia la política global de EOL ni dependencias. Los artefactos de QA, capturas, configuraciones de ejecución y medios permanecen fuera de Git.

## Revisión independiente

La revisión técnica detectó cinco problemas: retorno al ejemplo durante carga/error API, contraste del estado conectado, selección de una cuenta inactiva, acceso por teclado a los valores horarios y salto de línea de la comparación en tablet. Se corrigieron los cinco y la revisión de confirmación no dejó pendientes de esos hallazgos.

La revisión visual/UX aceptó la dirección y detectó pérdida potencial del borrador al abrir otra cuenta. El editor ahora exige guardar o cancelar antes de cambiar de cuenta. La confirmación validó ese arreglo; no constituye certificación integral de accesibilidad ni una nueva puntuación de toda la interfaz.

Se comprobó desconexión y recuperación del servicio: el histórico real muestra un error recuperable, el ejemplo permanece disponible y, al volver el servicio, reaparecen los registros API y el estado conectado. La regresión integrada de la muestra B completó 300/300 frames y produjo un MP4 de 1920×1080, 30 FPS y 300 frames, sin cambiar percepción ni configuración.

Las capturas se revisaron a 1920, 1366, 768 y 390 píxeles. Para Usuarios se utilizaron capturas nativas del viewport por una limitación de captura de página completa; no se presentan como capturas full-page. Las pruebas automatizadas y la inspección visual no sustituyen una revisión con lector de pantalla real.
