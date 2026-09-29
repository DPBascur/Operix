# OP-61 — Ejecutar y documentar el PoC técnico

## Estado y trazabilidad

Ejecución y validación local completadas el 21/09/2026. La ejecución integrada y
consolidación documental fueron revisadas y aprobadas para cierre formal de OP-61.
Issue de trazabilidad: #8. Arquitectura vigente: Operix Architecture v1.0.

- Código ejecutado: `54e163cc1e07ffbcdc334930dfd2a4264c720225`, rama `dev`.
- Árbol limpio antes de las pruebas y ejecución; HEAD coincidía con `origin/dev`
  y con la referencia remota consultada. Los cambios posteriores son documentales.
- Inicio: `2026-09-21T18:42:41-03:00`; fin: `2026-09-21T18:42:56-03:00`.
- Esas marcas delimitan la invocación; no constituyen una medición FPS/latencia.
- Fuente académica exclusiva: `Backlog-TT-DanielPena-V0.8.xlsm`, hoja
  `Backlog General`, fila 65. No se modifica el Excel.
- Requisitos: RF-01/02/03; RNF-02; R-01. Objetivos: OE-2 / OE-3.
- Dependencias formales: OP-43 y OP-60, cerradas. Etapa 2, prioridad Alta.

## Criterio de cierre y evidencia esperada

> Ejecución reproducible con video identificado, commit, configuración, salida visual y métricas; documentar cobertura de clases y fallos observados.

> Esperada: informe breve de PoC, video anotado, logs y ficha del entorno.

Esta evidencia demuestra la integración inicial del pipeline base del Motor. No
equivale a validación completa de los requisitos ni del sistema preventivo Operix.

## Ejecución integrada

Se reutilizó `engine/scripts/track_video.py`, sin otro orquestador ni cambios de
código, dependencias, lock o arquitectura:

`RecordedVideoSource → YoloDetector → filtro person → ByteTracker → TrajectoryAccumulator → OpenCvRenderer → VideoWriter`

El orquestador actualiza el tracker una vez por frame, escribe tracks en JSONL y
genera un video anotado. Se ejecutó una vez en un proceso nuevo, con estado inicial
nuevo de tracker y acumulador. Se procesaron los 277 frames completos, sin exclusión
de warm-up para esta demostración funcional.

### Entrada y pesos

| Campo | Valor |
| --- | --- |
| Dataset | NVIDIA PhysicalAI WorldModel Synthetic Warehouse Operations Scenes |
| Repositorio de datos | `nvidia/PhysicalAI-WorldModel-Synthetic-Warehouse-Operations-Scenes` |
| Revisión | `d5b88d3abcf659f304a107f4336b71b4e2159133` |
| Escenario | `warehouse_fire` |
| Run ID | `00023b5323028ab83e67_run_6_seed_1486583949` |
| Seed / cámara | `1486583949` / `ceiling_04` |
| Video | `00023b5323028ab83e67_run_6_seed_1486583949.ceiling_04.rgb.mp4` |
| Tamaño | 14.668.288 bytes |
| Propiedades | 1920×1080, 30 FPS, 277 frames, 9,233 s |
| SHA-256 video | `3ABE9043EE41F898D869890E8636B804186BFAF524DAEA2E6F6831E72711F4D6` |
| Modelo / pesos | YOLO11n-COCO / `yolo11n.pt`, 5.613.764 bytes |
| SHA-256 pesos | `0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1` |

Ambos hashes y los metadatos declarados por OpenCV fueron comprobados antes de
ejecutar. El script volvió a comprobar el hash y los metadatos de entrada. Se
reutilizaron recursos existentes fuera del repositorio, sin descargas. Procedencia,
selección y licencia documentadas en [OP-18](OP-18-data-selection.md); identificación
de la muestra principal en [OP-35](OP-35-bytetrack.md).

### Configuración y comando reproducible

YOLO: CUDA, `imgsz=640`, confianza `0.10`, IoU `0.70`; filtro exclusivo `person` en
el orquestador. ByteTrack: high `0.25`, low `0.10`, new `0.25`, buffer `30`, match
`0.80`, `fuse_score=true`. Visualización: caja `2`, fuente `0.55`, texto `2`, línea
de trayectoria `2`, historial `60` puntos, retención `30` frames.

Desde la raíz del repositorio, definir las siguientes variables con las ubicaciones
externas de los recursos y un directorio de salida nuevo. Los marcadores evitan
registrar rutas privadas. Los argumentos son los utilizados en la ejecución:

```powershell
$pocVideo = '<video ceiling_04 identificado arriba>'
$pocWeights = '<pesos yolo11n.pt identificados arriba>'
$pocOutput = '<directorio externo nuevo para esta ejecución>'
$env:YOLO_AUTOINSTALL = 'false'
$env:YOLO_CONFIG_DIR = (Resolve-Path '.\engine\.venv').Path
# Verificar los SHA-256 de entrada contra la tabla antes de ejecutar.
Get-FileHash -LiteralPath $pocVideo, $pocWeights -Algorithm SHA256
# Usar un directorio inexistente para no sobrescribir artefactos anteriores.
New-Item -ItemType Directory -Path $pocOutput -ErrorAction Stop | Out-Null
& .\engine\.venv\Scripts\python.exe .\engine\scripts\track_video.py $pocVideo `
  --weights $pocWeights `
  --output-jsonl "$pocOutput/op61-ceiling04-tracks.jsonl" `
  --output-video "$pocOutput/op61-ceiling04-annotated.mp4" `
  --expected-video-sha256 3ABE9043EE41F898D869890E8636B804186BFAF524DAEA2E6F6831E72711F4D6 `
  --expected-frames 277 --expected-fps 30 --expected-width 1920 --expected-height 1080 `
  --conf 0.10 --device cuda --imgsz 640 --iou 0.70 `
  --track-high-thresh 0.25 --track-low-thresh 0.10 --new-track-thresh 0.25 `
  --track-buffer 30 --match-thresh 0.80 `
  2> "$pocOutput/execution-stderr.log" |
  Tee-Object "$pocOutput/execution-summary.json"
if ($LASTEXITCODE -ne 0) { throw 'Falló la ejecución integrada' }
```

`person`, 60 puntos y retención 30 son la configuración efectiva del script con
estos argumentos, no opciones CLI adicionales. No se pasa `--no-fuse-score`.
El stdout capturado contiene el resumen JSON; al analizarlo debe respetarse la
codificación que utilice la versión local de PowerShell/Tee-Object.

## Entorno verificado

| Elemento | Valor |
| --- | --- |
| SO / arquitectura | Windows 10, build 19045 / AMD64 |
| CPU | AMD Ryzen 5 5500 |
| RAM | 34.244.796.416 bytes |
| GPU / VRAM | NVIDIA GeForce RTX 3070 / 8.589.410.304 bytes |
| Driver NVIDIA | 616.92 |
| Python | 3.12.10 x64 |
| PyTorch / TorchVision | 2.14.0+cu130 / 0.29.0+cu130 |
| CUDA incluida en PyTorch | 13.0 |
| OpenCV | paquete opencv-python 5.0.0.93; runtime 5.0.0 |
| Ultralytics / lap | 8.4.146 / 0.5.12 |
| operix-engine | 0.1.0 |

No se instalaron dependencias ni se modificaron versiones.

## Pruebas previas a la ejecución final

Se habilitaron ambas integraciones reales con `OPERIX_YOLO11_WEIGHTS`,
`OPERIX_OP18_VIDEO` (muestra original `ceiling_00`) y `OPERIX_OP35_VIDEO`
(`ceiling_04`), todos externos. La suite terminó antes de ejecutar el PoC final.

```powershell
.\engine\.venv\Scripts\python.exe -m pip check
.\engine\.venv\Scripts\python.exe .\engine\scripts\check_environment.py --require-cuda
.\engine\.venv\Scripts\python.exe -m unittest discover -s .\engine\tests -v
```

- `pip check`: `No broken requirements found`, salida 0.
- Entorno: salida 0; CUDA disponible, RTX 3070 detectada, tensor CUDA y CPU OK,
  prueba OpenCV OK; importaciones requeridas correctas.
- Suite: `Ran 55 tests in 5.476s`, `OK`, sin omisiones ni fallos.
- Desglose: OP-33 4/4; OP-34 9/9; OP-35 16/16; OP-60 15/15; OP-43 11/11.
- El diagnóstico `moov atom not found` corresponde a la prueba de archivo inválido,
  que aprueba; no proviene del video de validación.

## Resultados y comprobación de artefactos

| Comprobación | Resultado |
| --- | --- |
| Código de salida | 0 |
| Frames procesados / con person | 277/277 / 277/277 |
| Detecciones person | 1.088, contador del orquestador |
| Observaciones de tracks | 644, verificadas sumando el JSONL |
| IDs distintos | 8: 1, 2, 3, 4, 13, 28, 31, 36 |
| JSONL | 277 registros válidos; índices consecutivos 0…276 |
| Coherencia por ID | Primer/último frame, observaciones, gaps y recuperaciones coinciden con stdout |
| Video de salida | 277 frames decodificados íntegramente, todos 1920×1080; metadatos 30 FPS y 277 frames |
| Comparación histórica | Coinciden conteos y SHA-256 de JSONL/video con OP-60 |

El JSONL contiene tracks, no las detecciones crudas. Por ello permite auditar las
644 observaciones y los IDs; las 1.088 detecciones proceden del contador del script.
No se forzaron conteos ni se ajustaron parámetros. La coincidencia exacta de hashes
describe esta repetición en este entorno; no garantiza igualdad binaria universal.

| Artefacto externo nuevo | Tamaño (bytes) | SHA-256 |
| --- | ---: | --- |
| `op61-ceiling04-tracks.jsonl` | 150.547 | `ACAD8F3389233DE62652E590DD133ABE3B910FB91CD111BEDC00C96BA96C8DD5` |
| `op61-ceiling04-annotated.mp4` | 11.056.492 | `EA5B640009071D63D7EC756690E4437182C6DBCDD468CFE78DB0E4757735811A` |

Ambos artefactos son nuevos y no sobrescriben OP-35, OP-60 ni OP-43. El video dura
9,233 s. También quedan externos stdout, stderr, logs de pruebas/entorno y capturas
de inspección. Este informe y el resumen compacto constituyen la evidencia versionable.

**Evolución posterior del repositorio:** aquella ejecución utilizó recursos locales
externos y produjo salidas externas. Después se incorporaron en
[`assets/demo`](../../assets/demo/README.md) copias verificadas de las dos entradas
sintéticas y de este video anotado. El JSONL, los pesos, las capturas y los logs
siguen fuera de Git. La incorporación de esos tres MP4 no modifica la fecha, los
conteos ni los hashes de la ejecución histórica.

## Revisión visual y continuidad

Se revisaron hojas de contacto de los frames 0, 58, 60, 61, 62, 70, 73, 74, 86,
97, 103, 141, 207, 211, 212, 213, 214, 217, 218, 250, 266, 267 y 276, con detalle
de los frames 74 y 213 a resolución original. La decodificación fue exhaustiva;
la revisión visual fue un muestreo dirigido, no anotación MOT frame a frame.

- Cajas, clase, confianza, IDs y trayectorias aparecen sobre el frame correspondiente.
  Los colores distinguen tracks; hay etiquetas superpuestas durante el cruce 207–217.
- El ID 4 duplica/intersecta la caja del ID 1 sobre la misma persona en los frames
  revisados 58, 74 y 86. Su desaparición en 60 y 62–73 concuerda con el JSONL.
- Los frames 61, 62 y 70 son compatibles con fragmentación de la persona seguida
  como ID 2 y luego ID 13. Se conserva como fragmentación probable, no como ID switch
  confirmado ni identidad física demostrada.
- El ID 28 es corto y visualmente espurio en los frames revisados 97 y 103.
- El ID 13 falta en 73 y 212 y reaparece en 74 y 213. En las vistas revisadas las
  trayectorias mantienen cortes, sin puentes ficticios sobre las pérdidas; concuerda
  con las pruebas específicas del renderer.
- El ID 36 está presente hasta 266 y no se dibuja desde 267. Parte de la persona aún
  es visible en el borde en 267: la desaparición del track no equivale exactamente a
  la salida física completa del cuadro. La trayectoria inactiva deja de dibujarse.

Automáticamente se verifican cuatro gaps con recuperación del mismo ID: dos del
ID 4 y dos del ID 13. Eso no acredita por sí solo identidad física correcta. No hay
ground truth MOT ni ID switches inequívocamente confirmados; no se reportan MOTA,
IDF1, HOTA ni una tasa formal de cambios de identidad.

## Consolidación de evidencia previa

| Tarea | Evidencia reutilizada |
| --- | --- |
| [OP-33](OP-33-video-processing.md) | Lectura secuencial, metadatos, recursos y errores controlados. |
| [OP-34](OP-34-yolo11-detection.md) | Muestra secundaria ceiling_00: 300 frames, 399 detecciones, 302 person; forklift ausente y confusiones documentadas. No se repite el experimento completo. |
| [OP-35](OP-35-bytetrack.md) | ByteTrack, configuración y continuidad con pérdidas, duplicaciones y fragmentación probable. |
| [OP-60](OP-60-visualization.md) | Renderer y trayectorias; resultados históricos preservados. Se corrigen únicamente comando y referencia de alcance de OP-61. |
| [OP-43](OP-43-performance.md) | Benchmark independiente, CSV, resumen, entorno y límites de medición. No se repiten sus 15 corridas. |

La muestra secundaria es `001e53453441935632ae_run_1_seed_1288693302.ceiling_00.rgb.mp4`,
escenario `forklift_human_nearmiss`, SHA-256
`E4795E873DCBDAAA4DC3D42F533052E3C1DB62D1D3EF786C2C90DD4D7681330B`.
En OP-34 el montacargas produjo confusiones `bus` 73, `truck` 2, `bench` 4 y
`suitcase` 18; ninguna se reinterpreta como `forklift`.

### Rendimiento reutilizado de OP-43

| Escenario independiente | FPS global | Media (ms/frame) | Mediana | p95 |
| --- | ---: | ---: | ---: | ---: |
| A: pipeline base de procesamiento | 56,572 | 17,677 | 17,208 | 21,092 |
| B: pipeline + visualización | 52,046 | 19,214 | 18,667 | 23,010 |
| C: con escritura de video | 31,150 | 32,096 | 31,142 | 37,323 |

Fuente: [CSV existente](OP-43-benchmark.csv) y [resumen existente](OP-43-benchmark-summary.json),
validación 15/09/2026. Cinco repeticiones por escenario, 20 frames de warm-up y
257 medidos por repetición: 1.285 por escenario, 3.855 filas en total.

Estas métricas no corresponden directamente a la nueva ejecución integrada:
`track_video.py` escribe JSONL y genera resúmenes; el escenario C de OP-43 no incluye
esa escritura JSONL. No se atribuye 31,150 FPS a esta invocación de OP-61 ni se
calcula otra cifra a partir de su duración de proceso.

A/B superaron en promedio los 30 FPS de la fuente bajo el entorno/configuración
documentados. C obtuvo 31,150 FPS globales, pero una repetición alcanzó 29,658 y su
p95 supera 33,33 ms. Se preserva el outlier C/repetición 2/frame 99: inferencia
243,283 ms y total 259,623 ms, incluido en las estadísticas. YOLO domina A/B;
visualización añade aproximadamente 1,395 ms/frame y escritura 12,084 ms/frame.
Son observaciones descriptivas, sin umbral universal ni optimizaciones en OP-61.

## Limitaciones y exclusiones

- COCO no contiene `forklift`; la validación principal filtra `person` y no demuestra
  tracking fiable de maquinaria ni cobertura completa de personas en cada frame.
- ByteTrack depende de la calidad de detección: existen pérdidas, duplicaciones,
  tracks espurios y fragmentación. Los IDs temporales no identifican personas.
- Sin ground truth MOT, la continuidad automática y las hipótesis visuales no son
  métricas formales ni prueba de identidad física.
- Las muestras son sintéticas y acotadas; existe brecha respecto de CCTV industrial
  real, otras cámaras, densidades, condiciones de iluminación y duraciones.
- El rendimiento depende de hardware/configuración y no acredita funcionamiento
  universal o sostenido en tiempo real.
- No se implementan reglas, zonas, proximidad, eventos, alertas, persistencia del
  sistema, backend, frontend, nuevos modelos, fine-tuning ni optimizaciones.

## Evaluación del hito

La ejecución reproducida, pruebas y artefactos sustentan un hito estable del pipeline
base del Motor. La consolidación fue aprobada para cierre formal de OP-61. Al cerrar
esa tarea todavía no se había ejecutado el merge `dev → main` ni creado el tag.
Posteriormente, tras la auditoría pre-release, `main` se actualizó por fast-forward
y se publicó el tag anotado `v0.1.0` sobre el commit
`b5a2fd258ca4102410a1f4c2b72faf771e41d8f7`. El release no declara terminado
el Motor completo ni el sistema preventivo.
