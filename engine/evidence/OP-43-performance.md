# OP-43 — Medir FPS y latencia

Fecha de validación: 2026-09-15

Rama: `dev`

Requisito asociado: RNF-02

## Criterio de cierre del Backlog V0.8

> Registrar FPS promedio y latencia promedio en ms/cuadro, límites de medición,
> cuadros medidos, hardware, software, pesos y resolución.

Evidencia esperada: log/CSV de métricas y ficha reproducible del entorno, sin
resultados anticipados. El backlog no establece un umbral universal.

## Metodología

Se midió el estado actual del flujo secuencial:

```text
Video → OpenCV → YOLO11n → filtro person → ByteTrack → visualización → escritura
```

La implementación usa `time.perf_counter_ns()`. Cada inferencia CUDA se sincroniza
inmediatamente antes de iniciar el reloj de inferencia y después de ejecutar el
detector. La latencia total de cada frame comienza antes de solicitar el siguiente
frame a OpenCV y termina después de la última operación habilitada en el escenario.

`VideoWriter.release()` no se atribuye a un frame. Se registra por repetición y se
agrega únicamente al tiempo end-to-end del escenario C. La inicialización del modelo,
apertura de fuentes, validación de hashes y creación de objetos quedan fuera de las
ventanas medidas.

El FPS principal se calcula como:

```text
FPS global = total de frames medidos / tiempo total acumulado
```

No se promedian valores instantáneos `1 / latencia_frame`. El percentil 95 utiliza
nearest-rank: el valor ordenado en `ceil(0,95 × n)`.

Por cada escenario se ejecutaron cinco repeticiones. En cada repetición se procesaron
20 frames de warm-up y se midieron los 257 restantes. Se reutilizó una sola instancia
cargada de YOLO11 dentro del proceso y se reiniciaron ByteTrack y el acumulador de
trayectorias antes de cada repetición. El orden se rotó entre A/B/C para reducir el
sesgo temporal y térmico.

## Escenarios

| Escenario | Alcance |
| --- | --- |
| A | Pipeline base de procesamiento: lectura, YOLO11n, filtro `person` y ByteTrack; sin renderer ni escritura. |
| B | Escenario A más `TrajectoryAccumulator` y `OpenCvRenderer`; sin escritura. |
| C | Escenario B más escritura OpenCV y finalización de `VideoWriter`. |

## Muestra y configuración

| Campo | Valor |
| --- | --- |
| Escenario de datos | `warehouse_fire` |
| Archivo | `00023b5323028ab83e67_run_6_seed_1486583949.ceiling_04.rgb.mp4` |
| Cámara | `ceiling_04` |
| SHA-256 | `3ABE9043EE41F898D869890E8636B804186BFAF524DAEA2E6F6831E72711F4D6` |
| Resolución | 1920×1080 |
| FPS de la fuente | 30 |
| Frames | 277 |
| Warm-up | 20 frames por repetición |
| Frames medidos | 257 por repetición; 1.285 por escenario |
| Repeticiones | 5 por escenario |

Configuración fija:

| Componente | Configuración |
| --- | --- |
| Detector | YOLO11n-COCO, `yolo11n.pt` |
| SHA-256 de pesos | `0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1` |
| YOLO | `imgsz=640`, confianza `0.10`, IoU `0.70`, dispositivo `cuda` |
| Clases para tracking | `person` |
| ByteTrack | high `0.25`, low `0.10`, new `0.25`, buffer `30`, match `0.80`, fuse score activo |
| Visualización | caja `2`, fuente `0.55`, texto `2`, trayectoria `2`, longitud `60`, retención `30` |

## Entorno

| Elemento | Valor |
| --- | --- |
| Sistema | Windows 10 AMD64 |
| CPU | AMD Ryzen 5 5500 |
| RAM | 34.244.796.416 bytes (31,89 GiB) |
| GPU | NVIDIA GeForce RTX 3070 |
| VRAM | 8.589.410.304 bytes (8 GiB) |
| Driver NVIDIA | 616.92 |
| Python | 3.12.10 |
| PyTorch | 2.14.0+cu130 |
| TorchVision | 0.29.0+cu130 |
| CUDA incluida en PyTorch | 13.0 |
| OpenCV | 5.0.0 |
| Ultralytics | 8.4.146 |
| lap | 0.5.12 |
| operix-engine | 0.1.0 |

## Resultados globales

| Escenario | Frames | Tiempo acumulado (s) | FPS global | FPS por repetición |
| --- | ---: | ---: | ---: | --- |
| A | 1.285 | 22,715 | **56,572** | 58,184; 55,987; 58,231; 57,188; 53,544 |
| B | 1.285 | 24,690 | **52,046** | 53,760; 51,120; 50,920; 50,532; 54,122 |
| C | 1.285 | 41,252 | **31,150** | 33,217; 31,170; 29,658; 31,136; 30,778 |

Los tres resultados corresponden exclusivamente al hardware, muestra y configuración
documentados. El escenario A evidencia una capacidad promedio de procesamiento
superior a la tasa de 30 FPS de la fuente. El escenario C también queda ligeramente
por encima en promedio global, pero una repetición obtuvo 29,658 FPS y el p95 supera
33,33 ms. Por ello no se declara cumplimiento absoluto de tiempo real.

## Latencia total por frame

| Escenario | Promedio (ms) | Mediana (ms) | Mínimo (ms) | Máximo (ms) | Desv. estándar (ms) | p95 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | **17,677** | 17,208 | 13,773 | 28,476 | 1,942 | **21,092** |
| B | **19,214** | 18,667 | 14,398 | 60,596 | 2,936 | **23,010** |
| C | **32,096** | 31,142 | 26,079 | 259,623 | 9,169 | **37,323** |

## Desglose por etapa

Valores promedio y p95 en milisegundos por frame:

| Escenario | Lectura | Inferencia | Tracking | Visualización | Escritura |
| --- | ---: | ---: | ---: | ---: | ---: |
| A promedio | 2,406 | 14,209 | 0,792 | n.a. | n.a. |
| A p95 | 3,000 | 17,444 | 1,148 | n.a. | n.a. |
| B promedio | 2,297 | 14,474 | 0,784 | 1,395 | n.a. |
| B p95 | 2,815 | 17,930 | 1,118 | 1,876 | n.a. |
| C promedio | 2,382 | 15,207 | 0,771 | 1,371 | 12,084 |
| C p95 | 2,933 | 19,041 | 1,112 | 1,824 | 14,396 |

El FPS del núcleo detección + tracking, calculado también como razón global, fue
66,665 FPS en A, 65,541 FPS en B y 62,587 FPS en C. Este valor complementario excluye
lectura, render y escritura; no reemplaza el FPS global de cada escenario.

La finalización del writer en las cinco repeticiones de C fue 1,536; 1,655; 1,901;
1,722 y 1,494 ms. Esos tiempos están incluidos en el FPS global C, pero no en la
latencia individual de los frames.

## Observaciones

- La inferencia YOLO11 es la etapa dominante en A y B.
- La visualización agrega aproximadamente 1,395 ms promedio por frame.
- La escritura agrega 12,084 ms promedio y constituye el principal coste incremental
  del escenario C.
- En C, repetición 2, frame 99, se observó una inferencia aislada de 243,283 ms y una
  latencia total de 259,623 ms. Se conserva en las estadísticas; no se eliminan
  outliers sin una causa demostrada.
- La diferencia entre mediana y máximo de C confirma que el promedio por sí solo no
  describe toda la variabilidad temporal.
- La muestra es sintética, dura 9,23 segundos y usa una sola resolución, cámara y
  configuración. Los resultados no se generalizan a captura en vivo ni a otros
  equipos.
- Posibles optimizaciones de inferencia, codificación o E/S quedan como trabajo futuro.
  OP-43 no modifica ni optimiza el pipeline medido.

## Artefactos

| Artefacto | Uso |
| --- | --- |
| `engine/evidence/OP-43-benchmark.csv` | 3.855 mediciones por frame y etapa. |
| `engine/evidence/OP-43-benchmark-summary.json` | Entorno, configuración, orden y resumen estadístico. |
| `engine/evidence/OP-43-performance.md` | Metodología, resultados, límites e interpretación. |

El video final del escenario C se generó fuera del repositorio con 257 frames,
1920×1080, 30 FPS y 10.134.870 bytes. Su SHA-256 es
`774741031B4177CD58F07C2944998D554424A9A07CF3483BC8789EC0B8802A03`.
En el benchmark original, pesos, video de entrada, salida C, capturas y logs
temporales estaban fuera del repositorio. Posteriormente se incorporó una
[copia verificada de la entrada](../../assets/demo/README.md), pero **la salida
C del benchmark no está versionada**. Pesos, capturas y logs siguen fuera de Git.

Comando reproducible, usando una ruta local para los pesos y un **destino nuevo**
fuera del repositorio. No apuntar a los CSV/JSON históricos versionados: el
script escribe las salidas indicadas y puede sobrescribir el video de salida.

```powershell
$weights = '<ruta local a yolo11n.pt>'
if ((Get-FileHash -LiteralPath $weights -Algorithm SHA256).Hash -ne '0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1') { throw 'Los pesos no coinciden con el experimento' }
$benchmarkOut = Join-Path $env:TEMP ('operix-benchmark-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $benchmarkOut -ErrorAction Stop | Out-Null
.\engine\.venv\Scripts\python.exe .\engine\scripts\benchmark_pipeline.py `
  .\assets\demo\warehouse_fire_ceiling04.mp4 `
  --weights $weights `
  --video-sha256 3ABE9043EE41F898D869890E8636B804186BFAF524DAEA2E6F6831E72711F4D6 `
  --output-csv (Join-Path $benchmarkOut 'benchmark.csv') `
  --output-summary (Join-Path $benchmarkOut 'summary.json') `
  --output-video (Join-Path $benchmarkOut 'scenario-c.mp4')
```

## Límites de interpretación

La expresión “capacidad promedio de procesamiento cercana o superior a la tasa de
30 FPS de la fuente” solo se aplica al escenario, equipo y configuración documentados.
No equivale a garantía de latencia sostenida, procesamiento en vivo ni validación de
todo el Motor futuro de Operix. El escenario A representa el pipeline base de
procesamiento.
