# Avisos factuales de terceros

Este documento identifica materiales y dependencias usados por el prototipo;
**no emite conclusiones jurídicas**. El código fuente propio de Operix académico
se distribuye bajo [AGPL-3.0-or-later](LICENSE); ello no relicencia los
materiales de terceros descritos aquí.

## Videos sintéticos NVIDIA

Los dos clips de entrada y el material visual subyacente de la salida anotada
en [`assets/demo/`](assets/demo/README.md) proceden de **NVIDIA PhysicalAI
WorldModel Synthetic Warehouse Operations Scenes**, revisión
`d5b88d3abcf659f304a107f4336b71b4e2159133`. El proveedor identifica la
licencia **OpenMDW-1.1**. El [NOTICE](third_party/nvidia-warehouse-dataset/NOTICE.md)
incluye los tres archivos, origen, hashes y enlaces al
[dataset](https://huggingface.co/datasets/nvidia/PhysicalAI-WorldModel-Synthetic-Warehouse-Operations-Scenes)
y al [texto de licencia](https://openmdw.ai/license/1-1/). Operix no reclama
titularidad sobre las imágenes originales; la salida anotada añade únicamente
superposiciones técnicas al clip NVIDIA.

Los tres MP4 conservan los términos **OpenMDW-1.1** y los avisos de origen
aplicables; no se relicencian bajo AGPL-3.0-or-later.

## Ultralytics y pesos YOLO11

El Motor declara la dependencia `ultralytics` en
[`engine/pyproject.toml`](engine/pyproject.toml) y fija la versión validada
**8.4.146** en el [lock Windows/CUDA](engine/requirements.windows-cu130.lock.txt)
empleado en las evidencias experimentales. Una instalación genérica no fijada
puede resolver otra versión compatible; la prueba limpia en CPU resolvió
**8.4.166** y aprobó 126 pruebas, con 2 omisiones opcionales. Este resultado
no altera las evidencias históricas del entorno Windows/CUDA.

La biblioteca se instala como dependencia: **no está vendorizada** aquí.
La distribución utilizada declara **AGPL-3.0**. Operix utiliza `YOLO` desde
`ultralytics` y `BYTETracker` desde
`ultralytics.trackers.byte_tracker.BYTETracker`; no utiliza como dependencia
directa el repositorio independiente de ByteTrack publicado bajo MIT.
Ultralytics [documenta su licencia AGPL-3.0 y opción Enterprise](https://docs.ultralytics.com/help/contributing/).
La línea base experimental usó los pesos oficiales `yolo11n.pt` para detección
COCO. Los pesos **no están redistribuidos** en este repositorio. La
[evidencia OP-34](engine/evidence/OP-34-yolo11-detection.md) registra su SHA-256
y la [documentación oficial de YOLO11](https://docs.ultralytics.com/models/yolo11/)
describe el modelo y las licencias de los modelos/pesos. El Motor requiere una
copia local de los pesos y no los incluye en Git.

## Dependencias adicionales

El entorno Windows/CUDA validado fija `ultralytics-thop==2.1.6` en el
[lock](engine/requirements.windows-cu130.lock.txt). Su distribución instalada
declara **AGPL-3.0**; se instala como paquete externo, no como código
vendorizado de Operix. Las demás dependencias se instalan externamente según
el [proyecto Python](engine/pyproject.toml) y el lock; sus licencias no se
sustituyen por la licencia del código propio de Operix.
