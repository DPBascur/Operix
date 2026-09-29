# Clips de demostración

Estos tres MP4 son la excepción deliberada a la exclusión general de videos en
[`.gitignore`](../../.gitignore). El material visual procede del dataset sintético
**NVIDIA PhysicalAI WorldModel Synthetic Warehouse Operations Scenes**, revisión
`d5b88d3abcf659f304a107f4336b71b4e2159133`. Su origen, SHA-256,
atribución y licencia OpenMDW-1.1 están en el
[NOTICE de NVIDIA](../../third_party/nvidia-warehouse-dataset/NOTICE.md).
No son imágenes industriales reales ni material visual creado por Operix.

| Archivo | Función | Evidencia relacionada |
| --- | --- | --- |
| [`forklift_human_nearmiss_ceiling00.mp4`](forklift_human_nearmiss_ceiling00.mp4) | Entrada persona–montacargas; evidencia de la limitación de `forklift` en COCO | [OP-34](../../engine/evidence/OP-34-yolo11-detection.md) |
| [`warehouse_fire_ceiling04.mp4`](warehouse_fire_ceiling04.mp4) | Entrada principal para tracking y PoC, 277 frames a 1920×1080 y 30 FPS | [OP-35](../../engine/evidence/OP-35-bytetrack.md), [OP-61](../../engine/evidence/OP-61-poc.md) |
| [`warehouse_fire_ceiling04_operix_annotated.mp4`](warehouse_fire_ceiling04_operix_annotated.mp4) | Salida visual anotada sobre el segundo clip; las superposiciones fueron generadas por Operix, pero el video subyacente sigue siendo material NVIDIA | [OP-60](../../engine/evidence/OP-60-visualization.md), [OP-61](../../engine/evidence/OP-61-poc.md) |

Para inspección rápida, reproducir la entrada `warehouse_fire_ceiling04.mp4` y su
salida anotada en un reproductor MP4. Los IDs son temporales; las pérdidas,
duplicaciones y fragmentación documentadas no equivalen a identificación de
personas. No existe ground truth MOT ni validación industrial. La demo filtra
`person`; YOLO11n-COCO no contiene una clase explícita `forklift`.

## Reproducir el procesamiento

Desde la raíz del repositorio, con el entorno Windows/NVIDIA de la
[guía del Motor](../../engine/README.md#entorno-local) ya preparado, proporcionar
una copia **local** de los pesos oficiales `yolo11n.pt`. No están incluidos en Git;
su procedencia y obtención se explican en la
[sección de detección](../../engine/README.md#detección-de-objetos). Verificar su
SHA-256 antes de ejecutar:

```powershell
$weights = '<ruta local a yolo11n.pt>'
if ((Get-FileHash -LiteralPath $weights -Algorithm SHA256).Hash -ne '0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1') { throw 'Los pesos no coinciden con el experimento' }
$demoRun = Join-Path $env:TEMP ('operix-demo-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $demoRun -ErrorAction Stop | Out-Null
.\engine\.venv\Scripts\python.exe .\engine\scripts\track_video.py .\assets\demo\warehouse_fire_ceiling04.mp4 `
  --weights $weights `
  --output-jsonl (Join-Path $demoRun 'tracks.jsonl') `
  --output-video (Join-Path $demoRun 'annotated.mp4') `
  --expected-video-sha256 3ABE9043EE41F898D869890E8636B804186BFAF524DAEA2E6F6831E72711F4D6 `
  --expected-frames 277 --expected-fps 30 --expected-width 1920 --expected-height 1080 `
  --conf 0.10 --iou 0.70 --imgsz 640 --device cuda `
  --track-high-thresh 0.25 --track-low-thresh 0.10 --new-track-thresh 0.25 `
  --track-buffer 30 --match-thresh 0.80
```

El script filtra `person` y produce JSONL/video **nuevos fuera del repositorio**.
El MP4 versionado es el resultado histórico verificado de OP-60/61; una nueva
codificación no tiene por qué ser idéntica bit a bit. No sobrescribir evidencias
versionadas ni atribuir al clip una clasificación automática de Near Miss.
