# OP-37 — Variables espacio-temporales descriptivas

## Objetivo y criterio

Backlog V0.9: «Para un escenario etiquetado, el componente entrega las variables
declaradas con unidades y referencia temporal documentadas». Evidencia esperada:
«Salida tabular y prueba contra escenario conocido». Dependencias: OP-35 y OP-36.
La observación de alcance pide implementar solo variables requeridas por la regla
del MVP; este módulo produce datos sin evaluar todavía esa regla.

OP-35 aporta `Track` por frame y documenta pérdidas, recuperaciones y posibles
duplicados de IDs. OP-36 aporta `NormalizedPoint`, el centro inferior de la caja
y el test de pertenencia al polígono. OP-37 reutiliza esas interfaces sin cambiar
ByteTrack, el detector, los modelos de configuración ni la arquitectura v1.0.

## API y unidades

`operix_engine.spatiotemporal` ofrece `SpatiotemporalAnalyzer`,
`FrameSpatialState`, `ObjectSpatialState`, `ZoneMembershipState`,
`TrajectorySample` y `PairwiseProximity`. Los tipos de salida son inmutables.
`update(frame_index, tracks)` recibe exclusivamente `Track` de Operix y entrega
los objetos y pares observados en ese frame. `reset()` inicia otra secuencia.

| Variable | Definición | Unidad / referencia |
| --- | --- | --- |
| `timestamp_s` | `frame_index / fps` | Segundos desde el comienzo del video; no es hora real. Depende del FPS declarado y validado. |
| `position` | `((x_min+x_max)/(2×width), y_max/height)` | Coordenadas normalizadas del plano de imagen en `[0,1]`, reutilizando OP-36. |
| `inside` | `point_in_zone(position, zone)` | Booleano; borde y vértices cuentan como dentro según OP-36. |
| `dwell_time_s` | `(frame_index - primer_frame_consecutivo_dentro) / fps` | Segundos observados transcurridos en el intervalo actual; vale 0 al entrar y al salir. |
| `trajectory` | Hasta 60 muestras recientes consecutivas `(frame_index, timestamp_s, position)` | Frames, segundos y coordenadas normalizadas. |
| `normalized_distance` | `sqrt((x_a-x_b)^2 + (y_a-y_b)^2)` | Distancia normalizada en el plano de imagen entre centros inferiores del mismo frame. |

El analyzer acepta `width`, `height`, `fps`, las zonas de `OperationalConfig` y
un límite acotado de muestras de trayectoria (60 por defecto). Rechaza FPS,
dimensiones, índices, IDs duplicados, cajas o zonas inválidas. Ordena los tracks
por ID para producir pares deterministas `track_id_a < track_id_b`. Las zonas son
las de la vista configurada; el llamador debe verificar la correspondencia de
`view_id` con el video. El script de evidencia sí la verifica.

### Continuidad y gaps

Solo se acumula permanencia cuando **el mismo ID está observado dentro de la
zona en frames consecutivos**. Un frame sin ese track, un salto en `frame_index`
o una salida de la zona rompe el intervalo. Una reentrada empieza en 0 s. No se
interpolan observaciones ausentes ni se equipara la recuperación de ByteTrack con
identidad física demostrada. En un frame vacío no se emiten estados de objetos
ni pares. Una nueva secuencia requiere `reset()`.

`TrajectoryAccumulator` de OP-60 conserva centros de caja en píxeles para el
renderer y puede retener historial visual durante gaps. No sirve como historial
de estas variables espacio-temporales: OP-37 mantiene un `deque` pequeño de **centros inferiores
normalizados**, con tiempo de video, y corta la trayectoria en los mismos gaps
conservadores. No se modificó la visualización.

## Escenario etiquetado y salida tabular

- Escenario: `warehouse_fire`; cámara `ceiling_04`; video
  `00023b5323028ab83e67_run_6_seed_1486583949.ceiling_04.rgb.mp4`.
- Revisión NVIDIA: `d5b88d3abcf659f304a107f4336b71b4e2159133`.
- Video: SHA-256 `3ABE9043EE41F898D869890E8636B804186BFAF524DAEA2E6F6831E72711F4D6`,
  1920×1080, 30 FPS, 277 frames.
- Tracks reales: JSONL previamente generado en OP-35/OP-61, SHA-256
  `ACAD8F3389233DE62652E590DD133ABE3B910FB91CD111BEDC00C96BA96C8DD5`.
- Ventana analizada: frames **139–147** (9 frames consecutivos); IDs 1, 13 y
  31. Zona configurada: `zona_critica_01` de OP-30, vista `ceiling_04`.
- [Tabla por objeto/zona](OP-37-object-variables.csv): 25 filas. Incluye frame,
  tiempo, ID, clase, posición, zona, pertenencia, permanencia y frames de
  trayectoria reciente.
- [Tabla de pares](OP-37-pairwise-proximity.csv): 23 filas, con IDs ordenados y
  distancia normalizada en cada frame.

Resultados verificables: el ID 31 aparece dentro de la zona en el frame 141,
`timestamp_s=4.7`, posición `(0.334777, 0.603243)` y permanencia `0 s`.
Continúa observado dentro hasta el frame 147, con permanencia `0.2 s` y
trayectoria reciente en los frames `141;142;143;144;145;146;147`. Por ejemplo,
su posición cambia de `(0.334777, 0.603243)` en 141 a
`(0.333496, 0.604503)` en 142 y `(0.332357, 0.605213)` en 143; los tiempos
son `4.7`, `4.733333` y `4.766667 s` desde el inicio del video. Los IDs 1 y 13
permanecen fuera de la zona en la ventana. En el frame 141 la distancia
normalizada entre IDs 1 y 13 es `0.053932`; entre IDs 13 y 31 es `0.397714`.
No se interpreta ninguno de esos valores como cercanía física o peligro.

El script [analyze_spatiotemporal.py](../scripts/analyze_spatiotemporal.py)
reproduce ambos CSV desde el JSONL local, sin repetir inferencia ni descargar
pesos. Desde la raíz del repositorio, sustituir `<RUTA_JSONL_LOCAL>` por la
ruta autorizada del JSONL identificado arriba:

```powershell
.\engine\.venv\Scripts\python.exe .\engine\scripts\analyze_spatiotemporal.py <RUTA_JSONL_LOCAL> --expected-jsonl-sha256 ACAD8F3389233DE62652E590DD133ABE3B910FB91CD111BEDC00C96BA96C8DD5 --config .\engine\config\examples\op30-zone-rule.json --view-id ceiling_04 --width 1920 --height 1080 --fps 30 --start-frame 139 --end-frame 147 --output-objects <NUEVA_SALIDA_OBJETOS.csv> --output-pairs <NUEVA_SALIDA_PARES.csv>
```

El script exige salidas nuevas para no sobrescribir evidencia anterior. Los CSV
versionables no contienen rutas locales ni video; video, pesos y JSONL completo
permanecen fuera de Git.

## Pruebas y límites

Las pruebas unitarias de OP-37 cubren tiempo de video, posición/zonas de OP-36,
entrada, permanencia, salida, reentrada, gap por ausencia y por salto de frame,
trayectoria, pares simétricos y distancia cero, múltiples tracks/zonas, entradas
inválidas, FPS y dimensiones inválidos, estado inmutable y `reset()`.
Resultado local: **16/16 pruebas de OP-37** y **107/107 de la suite completa**,
incluidas las integraciones reales existentes. `pip check`: sin dependencias
rotas; `check_environment.py --require-cuda`: CPU, CUDA/RTX 3070 y OpenCV
operativos; `compileall`: sin errores.

**Las distancias calculadas en OP-37 corresponden al espacio normalizado de
imagen y no representan distancias físicas.** La perspectiva y la proporción
ancho/alto afectan su interpretación; no hay homografía ni calibración. Un
umbral numérico no puede trasladarse universalmente entre cámaras. La muestra es
sintética y limitada. ByteTrack puede perder, duplicar o fragmentar tracks; sus
IDs son temporales y no identifican personas. La permanencia aquí es duración
observada de un ID, no tiempo verdadero de ocupación si hubo oclusiones.

**OP-37 produce variables descriptivas. No determina riesgo ni genera eventos.**
OP-38 podrá evaluar condiciones configurables sobre `inside`, `dwell_time_s` y
`normalized_distance`; esa interpretación y sus umbrales quedan fuera de OP-37.
