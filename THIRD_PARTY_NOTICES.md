# Avisos factuales de terceros

Este documento identifica materiales y dependencias usados por el prototipo;
**no establece la licencia del código Operix ni emite conclusiones jurídicas**.

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

## Ultralytics y pesos YOLO11

El Motor declara la dependencia `ultralytics` en
[`engine/pyproject.toml`](engine/pyproject.toml) y fija la versión validada
**8.4.146** en el [lock Windows/CUDA](engine/requirements.windows-cu130.lock.txt).
La biblioteca se instala como dependencia: **no está vendorizada** aquí.
Ultralytics [publica información sobre AGPL-3.0 y su opción Enterprise](https://docs.ultralytics.com/help/contributing/).
La línea base experimental usó los pesos oficiales `yolo11n.pt` para detección
COCO. Los pesos **no están redistribuidos** en este repositorio. La
[evidencia OP-34](engine/evidence/OP-34-yolo11-detection.md) registra su SHA-256
y la [documentación oficial de YOLO11](https://github.com/ultralytics/yolo11)
describe el modelo y la obtención de pesos en el primer uso de Ultralytics.

El licenciamiento definitivo de Operix requiere una decisión separada antes
de la publicación. Ninguna mención de licencias de terceros aquí selecciona
una licencia para el código propio.
