# OP-30 — Configurar zonas y reglas operacionales

## Objetivo y criterio académico

Fuente vigente: `Backlog-TT-DanielPena-V0.9.xlsm`, hoja `Backlog General`,
fila 34. Historia de usuario de Etapa 2, prioridad Alta, asociada a RF-04/05 y
PV-01; dependencias OP-02, OP-03 y OP-11. Issue de gestión: [#11](https://github.com/DPBascur/Operix/issues/11), `In Progress` durante esta validación local.

> Se puede crear una zona y modificar al menos un parámetro de una regla sin
> cambiar el código del detector.

Evidencia esperada: demostración de configuración y archivo de parámetros.

## Diseño implementado

El archivo [op30-zone-rule.json](../config/examples/op30-zone-rule.json) define
una vista (`view_id`), zonas y reglas. `schema_version=1` permite reconocer el
contrato y rechazar versiones no soportadas. `coordinate_system=normalized` fija
vértices `x,y` en `[0,1]`; no se requiere una resolución de referencia para
almacenar la zona. La zona pertenece a la vista indicada: normalizar no hace
equivalentes cámaras, encuadres ni recortes distintos.

Se eligió JSON porque la estructura es pequeña, Python puede cargarla con su
biblioteca estándar, los tests pueden construir variantes sin GPU y los campos
son trasladables a una futura API/persistencia. YAML exigiría un parser declarado
como dependencia directa; TOML es menos natural para listas de vértices. No se
introdujeron dependencias nuevas.

`operix_engine.operational_config` expone `Zone`, `RuleConfig`,
`OperationalConfig`, `OperationalConfigError` y `load_operational_config(path)`.
Los modelos son dataclasses inmutables; las colecciones y parámetros anidados
también se congelan. El módulo no importa OpenCV, Ultralytics, YOLO, ByteTrack,
`Detection`, `Track` ni el renderer.

## Validaciones estructurales

- JSON UTF-8 válido, sin claves duplicadas ni constantes NaN/Infinity; raíz
  objeto con claves conocidas, versión de esquema `1`, `view_id` no vacío y
  sistema de coordenadas `normalized`.
- `zones` y `rules` son listas. Zona: ID y nombre no vacíos, IDs únicos,
  polígono de al menos tres vértices, cada uno con dos números finitos en `[0,1]`.
- Regla: ID no vacío y único, versión entera positiva, `enabled` booleano y
  `parameters` como objeto JSON no vacío con valores estructuralmente válidos.
  Si declara `zone_id`, este debe identificar una zona de la misma configuración.

No se comprueba si una duración es operacionalmente adecuada ni si una clase
detectada es compatible con la regla. `min_duration_s = 2.0` es únicamente un
parámetro demostrativo del escenario, no un umbral universal de seguridad.

## Demostración sin modificar percepción

La prueba `test_changing_parameter_in_json_changes_loaded_value_only` carga dos
archivos temporales con la misma zona y regla. El primero conserva
`min_duration_s=2.0`; en el segundo se cambia solo el JSON a `3.5`. El cargador
entrega respectivamente `2.0` y `3.5`, sin cambiar el detector, tracker ni su
código. La prueba de aislamiento verifica además que este módulo no importa los
backends de percepción.

Para inspeccionar el archivo de ejemplo desde la raíz del repositorio:

```powershell
.\engine\.venv\Scripts\python.exe -c "from operix_engine.operational_config import load_operational_config; c = load_operational_config('engine/config/examples/op30-zone-rule.json'); print(c.view_id, c.zones[0].zone_id, c.rules[0].parameters['min_duration_s'])"
```

Salida esperada: `ceiling_04 zona_critica_01 2.0`.

## Pruebas y resultado

```powershell
.\engine\.venv\Scripts\python.exe -m unittest discover -s .\engine\tests -p test_operational_config.py -v
```

Las pruebas de OP-30 cubren carga, tipos, inmutabilidad, cambios de parámetro,
schema, vista, duplicados, polígonos, valores fuera de rango/no finitos,
estructura de reglas, referencias y desacoplamiento. El resultado final de la
validación local previa al commit fue `17/17` pruebas propias y `75/75` en la
suite completa, con las dos integraciones reales existentes habilitadas.

## Límites y continuidad

**Configurar una regla no equivale a evaluarla.**

**La configuración de una zona no implica todavía determinar geométricamente la pertenencia de un objeto.**

OP-36 podrá utilizar `Zone` para definir, guardar y recuperar zonas y decidir
dentro/fuera; allí se definirá el punto de referencia geométrico del objeto.
OP-37 calculará variables espacio-temporales con unidades y tiempo documentados.
OP-38 consumirá parámetros configurados para evaluar condiciones y producir
eventos. Ninguno de esos comportamientos se implementa en OP-30.

Los pesos COCO actuales no incluyen una clase `forklift`; este ejemplo no prueba
una regla persona–montacargas ni valida umbrales operacionales con expertos. La
configuración queda acotada a la vista y el escenario definidos.
