# Etapa 4 · Resumen, indicadores e historial

## Auditoría de partida

Resumen e Indicadores usaban la misma pantalla y arrancaban con una colección ilustrativa en memoria. Al seleccionar la API, ya existían el total, la frecuencia diaria, los tipos y la comparación mensual. El navegador derivaba horas, zonas y actividad reciente a partir de la lista. El historial en modo API aplicaba fecha y tipo, pero los enlaces del panel no llevaban esos filtros. En modo mock, el historial mostraba candidatos simulados. El dossier consultaba el evento persistido, incluido PNG o clip cuando existían.

## Datos y permisos

Resumen abre con registros persistidos del mes UTC, muestra el total y los runs distintos con eventos y enlaza al dossier desde actividad reciente. Indicadores conserva la tendencia, las distribuciones por hora, tipo y zona, y añade procedencia y videos agrupados por SHA-256. El Backend usa el mismo filtro de fecha, tipo, procedencia y huella para la lista y las frecuencias. El panel comprueba que ambas respuestas coincidan en total, días y tipos. Los enlaces conservan los límites UTC inclusivos, incluida la última fracción de segundo.

Una demo declarada se identifica por `source.kind=demo`. Una carga manual puede ser un ensayo. Los históricos sin clasificación explícita quedan separados. Solo los videos con huella válida entran en el desglose por video. Un mismo archivo puede aparecer con varios nombres y se cuenta una sola vez como fuente identificada. El panel muestra hasta diez videos ordenados por número de eventos.

Administrador y responsable de seguridad consultan el historial del despliegue. El usuario opera sobre sus propios análisis temporales. El panel no consulta sesiones temporales. Un evento publicado y sus metadatos forman parte del historial compartido bajo los permisos vigentes. Se mantienen los permisos de clips y PNG. El publicador interno sigue limitado a crear eventos y adjuntar PNG.

El total de runs con eventos no incluye ejecuciones sin registros. Los conteos corresponden al momento registrado en `occurred_at`, que puede ser el ancla del análisis. El sistema carece de una clasificación fiable de operación frente a ensayo para cargas manuales e históricos, y de un catálogo persistente de todas las ejecuciones.

## Verificación

- Backend **142/142** con una instancia temporal de PostgreSQL. Se reconciliaron lista y frecuencias con datos controlados por fecha, tipo, procedencia y huella, incluyendo límites inclusivos y resultados vacíos. Pasaron las regresiones de sesión, permisos, publicación, clips y PNG.
- Frontend **43/43**, lint, typecheck y build aprobados. Chromium con API fixture verificó carga, filtros, resultado vacío, recuperación tras 503, navegación por video al historial filtrado y acceso al dossier con PNG y clip. La revisión responsive cubrió 18 combinaciones de ancho y ruta.
