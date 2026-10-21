# OP-41 — Frecuencias históricas básicas (propuesta autónoma)

## Alcance y trazabilidad

Backlog académico V0.11, OP-41, dependencias OP-32, OP-39 y OP-40.
Criterio: «Las frecuencias por período y tipo coinciden con un conteo
independiente del conjunto de prueba».

Se añade una consulta de solo lectura sobre el modelo `Event` existente y una
vista `/indicators` en modo API. No se cambian el backlog, Issues, Project,
modelo de persistencia, migraciones, reglas, tipos de evento ni percepción.
Es una propuesta en rama autónoma, pendiente de revisión e integración humana;
no declara cerrado el estado académico de OP-32/41 ni OP-40.

## Contrato

`GET /api/v1/events/frequencies/` acepta los mismos filtros inclusivos que
`GET /api/v1/events/`: `occurred_after`, `occurred_before` y `event_type`.
Las fechas requieren zona explícita. Actualmente solo se admite `zone_dwell`;
no se inventa otra categoría para completar una prueba de discriminación.

Una consulta PostgreSQL agrupa por día UTC y tipo. `total`, `by_period` y
`by_type` se derivan de ese único resultado, evitando combinar snapshots de
consultas diferentes. No se generan días vacíos. POST/PUT/DELETE devuelven 405.

La interfaz permite consultar, filtrar y limpiar filtros, con carga, error y
resultado vacío. Los controles Desde/Hasta representan días UTC completos.
No hay fallback silencioso a mocks. Los conteos incluyen registros de
desarrollo/demostración: no son tasas de incidentes, riesgo, personas únicas,
validación industrial ni una evaluación de efectividad preventiva.

## Verificación reproducible

Con el entorno del Backend configurado y PostgreSQL de pruebas disponible:

```powershell
python -B manage.py test apps.events.test_frequencies
```

Seis pruebas automáticas usan exclusivamente la base efímera de tests:

- Cuatro eventos conocidos se contrastan con un `Counter` independiente,
  incluyendo un timestamp con offset +03:00 que pertenece al día anterior UTC.
- Las sumas por día y tipo coinciden con el total; se verifica una sola consulta.
- Los límites inclusivos y el tipo coinciden con la lista filtrada de eventos.
- Rango vacío y base vacía no fabrican filas ni períodos.
- Filtros desconocidos, tipo inexistente, fecha sin zona y rango invertido se rechazan.
- La consulta no permite escrituras.

La revisión web local mostró 25 registros persistidos del entorno de desarrollo,
reconciliados con la lista existente. Ese número describe solo ese entorno y
no constituye un fixture requerido ni una métrica operacional del sistema.
