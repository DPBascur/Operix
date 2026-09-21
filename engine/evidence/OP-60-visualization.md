# OP-60 — Visualizar detecciones y tracks

## Criterio de cierre

> La visualización corresponde al cuadro y a sus detecciones/tracks; permite revisar continuidad de IDs y guardar evidencia de ejecución.

Evidencia esperada: video anotado o capturas y comando de reproducción.

## Alcance implementado

Se incorporó una visualización reutilizable del Motor que recibe un frame OpenCV y tipos públicos de Operix (`Detection` o `Track`) y devuelve una copia anotada. El renderer no abre videos, no ejecuta inferencia ni tracking y no persiste archivos.

La visualización incluye:

- bounding boxes;
- clase y confianza con dos decimales;
- `track_id` en observaciones de tracking;
- trayectorias recientes mantenidas fuera de `Track`.

Los scripts existentes conservan la responsabilidad de leer y escribir video, ejecutar YOLO11/ByteTrack y entregar los resultados al renderer.

## Diseño y configuración

Tipos incorporados:

- `VisualizationConfig`: configuración visual mínima e inmutable;
- `TrajectoryPoint`: centro del bounding box asociado a un índice de frame;
- `TrajectoryAccumulator`: historial externo por `track_id`;
- `OpenCvRenderer`: render de detecciones y tracks sobre una copia del frame.

Configuración usada en la validación:

| Parámetro | Valor |
| --- | ---: |
| Grosor de bounding box | 2 |
| Escala de fuente | 0,55 |
| Grosor de texto | 2 |
| Grosor de trayectoria | 2 |
| Longitud máxima de trayectoria | 60 puntos |
| Retención de tracks inactivos | 30 frames |

Los colores de tracks son deterministas por `track_id`. El acumulador conserva temporalmente el historial de tracks inactivos, pero el renderer dibuja únicamente tracks activos. Dos puntos se unen solo cuando pertenecen a frames consecutivos; una pérdida temporal no produce una línea artificial sobre el intervalo sin observaciones.

## Validación automatizada

Comandos ejecutados desde la raíz del repositorio:

```powershell
.\engine\.venv\Scripts\python.exe -m pip check
.\engine\.venv\Scripts\python.exe .\engine\scripts\check_environment.py --require-cuda
.\engine\.venv\Scripts\python.exe -m unittest discover -s .\engine\tests -v
```

Resultados:

- `pip check`: sin dependencias rotas;
- entorno: Python 3.12.10 x64, PyTorch 2.14.0+cu130, CUDA 13.0 disponible y NVIDIA GeForce RTX 3070 operativa;
- suite completa: 44/44 pruebas aprobadas;
- OP-33: 4/4;
- OP-34: 9/9;
- OP-35: 16/16;
- OP-60: 15/15.

Las pruebas de OP-60 utilizan frames, detecciones y tracks sintéticos; no descargan pesos ni requieren inferencia YOLO o ByteTrack real. Cubren copia e inmutabilidad del frame, bounding boxes y etiquetas, colores deterministas, trayectorias consecutivas, discontinuidades, retención, expiración, límite de longitud, reinicio y validación de entradas/configuración.

## Validación real sobre la muestra de OP-35

### Entrada

| Campo | Valor |
| --- | --- |
| Escenario | `warehouse_fire` |
| Archivo | `00023b5323028ab83e67_run_6_seed_1486583949.ceiling_04.rgb.mp4` |
| Run ID | `00023b5323028ab83e67_run_6_seed_1486583949` |
| Seed | `1486583949` |
| Cámara | `ceiling_04` |
| Resolución | 1920×1080 |
| FPS | 30 |
| Frames | 277 |
| SHA-256 | `3ABE9043EE41F898D869890E8636B804186BFAF524DAEA2E6F6831E72711F4D6` |

Se reutilizó la configuración validada en OP-35: YOLO11n-COCO, confianza 0,10, IoU 0,70, tamaño 640, dispositivo CUDA y filtro `person`; ByteTrack con umbrales 0,25/0,10/0,25, buffer de 30 frames, `match_thresh=0,80` y fusión de score activa.

Comando reproducible, manteniendo entradas y salidas fuera del repositorio:

```powershell
.\engine\.venv\Scripts\python.exe .\engine\scripts\track_video.py <video-entrada> --weights <pesos-locales> --output-jsonl <salida-jsonl> --output-video <video-anotado> --expected-video-sha256 3ABE9043EE41F898D869890E8636B804186BFAF524DAEA2E6F6831E72711F4D6 --expected-frames 277 --expected-fps 30 --expected-width 1920 --expected-height 1080 --conf 0.10 --iou 0.70 --imgsz 640 --device cuda --track-high-thresh 0.25 --track-low-thresh 0.10 --new-track-thresh 0.25 --track-buffer 30 --match-thresh 0.80
```

El filtro `person` está incorporado en el orquestador; no existe un argumento
`--class-name`. El comando se corrigió documentalmente durante OP-61 para reflejar
la interfaz vigente, sin alterar los resultados históricos siguientes.

Resultado de ejecución:

- 277/277 frames procesados;
- 1.088 detecciones `person`;
- 644 observaciones de tracking;
- 8 IDs emitidos;
- salida anotada: `op60-ceiling04-annotated.mp4`;
- salida: 1920×1080, 30 FPS y 277 frames;
- tamaño de salida: 11.056.492 bytes;
- SHA-256 del video anotado: `EA5B640009071D63D7EC756690E4437182C6DBCDD468CFE78DB0E4757735811A`;
- SHA-256 del JSONL: `ACAD8F3389233DE62652E590DD133ABE3B910FB91CD111BEDC00C96BA96C8DD5`.

Comando de reproducción:

```powershell
Start-Process <video-anotado>
```

El video anotado, el JSONL y las capturas de revisión permanecen fuera del repositorio.

## Inspección visual

Observaciones confirmadas visualmente:

- las etiquetas muestran clase, confianza e ID y permanecen dentro del frame, incluso cerca de los bordes;
- los IDs simultáneos usan colores distinguibles y deterministas;
- las trayectorias muestran únicamente el historial reciente del track activo;
- las pérdidas temporales de los IDs 4 y 13 no quedan conectadas por líneas artificiales;
- la salida del ID 36 deja de dibujar su trayectoria al desaparecer;
- en frames con personas superpuestas, especialmente entre los frames 207 y 217, se conservan cajas, etiquetas y trayectorias diferenciadas;
- la duplicación/track espurio del ID 4 continúa visible y no es ocultada por la capa de visualización;
- la secuencia compatible con fragmentación entre los IDs 2 y 13 se representa como historiales separados, sin inventar continuidad.

La inspección visual permite revisar continuidad, pérdidas, recuperaciones y fragmentación. Las asociaciones ID 2 → 13 siguen siendo una posibilidad técnica, no un cambio de ID confirmado. La muestra no dispone de ground truth de identidad, por lo que no se declaran métricas MOT ni conteos formales de ID switches.

## Límites

- La visualización es una herramienta técnica local del Motor, no un frontend ni un dashboard.
- No incorpora reproducción web, streaming, WebSocket ni overlays interactivos.
- No implementa reglas, zonas, proximidad, eventos ni persistencia.
- No constituye el benchmark formal de FPS/latencia de OP-43.
- OP-61 consolida la ejecución del PoC y sus evidencias; tampoco incorpora eventos operacionales.
- La superposición física de objetos puede provocar solapamiento temporal de etiquetas; se conserva la fidelidad del resultado del tracker sin alterar asociaciones.
