# OP-41 — Frecuencias históricas de eventos

## Alcance

Se integró al dashboard actual la consulta de frecuencias históricas de eventos persistidos en PostgreSQL. Se revisó el commit antecedente `48e1512` y se reutilizó su agregación Backend y sus pruebas; su antigua interfaz `/indicators` no se aplicó como *cherry-pick* porque el frontend vigente ya tenía un dashboard distinto. No se alteraron modelos, migraciones, reglas, percepción, tipos de evento ni el ejemplo ilustrativo. Esta evidencia técnica no modifica por sí sola el estado del backlog académico.

El criterio de OP-41 del backlog V0.11 es: «Las frecuencias por período y tipo coinciden con un conteo independiente del conjunto de prueba». La API `GET /api/v1/events/frequencies/` usa el mismo contrato de filtros inclusivos que `GET /api/v1/events/`: `occurred_after`, `occurred_before` y `event_type`, con zona horaria obligatoria en las fechas. Una consulta PostgreSQL agrupada por día UTC y tipo produce `total`, `by_period` y `by_type` reconciliados. No añade días sin datos; rechaza filtros inválidos y escrituras.

## Integración de la interfaz vigente

El selector del dashboard separa **Ejemplo ilustrativo** de **Registros API**. En modo API, cada cambio del mes UTC lanza consultas limitadas al mes seleccionado: frecuencias por día/tipo y lista de eventos para zona, hora y actividad reciente; una frecuencia adicional del mes UTC anterior sustenta la comparación. Las consultas no usan datos mock como fallback. Se verifica que el total de la lista coincida con el agregado; si los registros cambiaron entre consultas, se solicita actualizar en vez de mostrar cifras contradictorias. Los límites de mes incluyen el último microsegundo en UTC y el selector ofrece doce meses desde el mes actual. Un mes sin registros no exhibe KPIs cero como si fueran históricos significativos.

La prueba manual en navegador consultó el entorno PostgreSQL de desarrollo: octubre de 2026 mostró **25 registros**, 1 día con actividad y un único tipo (`zone_dwell`); septiembre de 2026 mostró el estado vacío. Volver a octubre actualizó las consultas y restauró los 25 registros. Estos conteos dependen de la base local en ese momento, no son métricas de incidentes ni un fixture requerido. El único tipo admitido actualmente es `zone_dwell`; no se creó una segunda categoría artificial. La UI indica UTC, y no se mezcla la zona del navegador con la agrupación.

## Verificación

Con PostgreSQL de prueba configurado, `python manage.py test apps.events.test_frequencies` ejecutó **6/6** pruebas: conteo independiente de cuatro eventos, cambio de día por offset horario, consistencia total/día/tipo, consulta única, límites inclusivos frente a la lista, base/rango vacíos, filtros inválidos y rechazo de escritura. La suite Backend completa aprobó **75/75**, `manage.py check` informó cero problemas y `makemigrations --check --dry-run` no encontró cambios. El frontend aprobó **21/21** pruebas, `lint`, `typecheck` y build. No se requieren nuevas dependencias.

Las frecuencias describen **registros técnicos persistidos**, incluidos posibles ensayos de desarrollo. No miden incidencia real, prevención, riesgo, identidades únicas ni validez industrial. La lista y el agregado son solicitudes separadas; una escritura concurrente puede producir una discrepancia temporal, que la interfaz comunica para reintentar.
