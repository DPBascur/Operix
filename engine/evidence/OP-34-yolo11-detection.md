# OP-34 — Integrar detección con YOLO11

## Estado y alcance

Implementación validada en la rama `dev` y aprobada para cierre formal. Esta
evidencia documenta el diseño, las pruebas y el resultado experimental de OP-34.

El alcance implementado es deliberadamente acotado:

```text
frame BGR uint8 -> detector YOLO11 -> tuple[Detection, ...]
```

No se incorporaron tracking, IDs temporales, trayectorias, reglas, proximidad,
zonas, eventos, persistencia ni una funcionalidad general de visualización. Tampoco
se realizó un benchmark formal de rendimiento.

## Criterio de cierre del Backlog V0.8

> Se obtienen detecciones en el video de prueba. Se documenta qué clases del
> escenario cubren los pesos y cuáles no.

La evidencia esperada es la salida del detector, los pesos y la configuración
utilizados, y un video anotado.

## Diseño implementado

- `operix_engine.detection` contiene tipos propios, inmutables y desacoplados de
  Ultralytics: `BoundingBox`, `Detection` y el protocolo `Detector`.
- Las cajas usan coordenadas de píxel `xyxy` de punto flotante.
- `Detection` contiene `class_id`, `class_name`, `confidence` y `bounding_box`.
  `frame_index` pertenece al flujo de video y no a la detección.
- `operix_engine.yolo_detector` adapta YOLO11 y convierte su resultado a los tipos
  de Operix sin filtrar clases ni exponer objetos internos de Ultralytics.
- El adaptador recibe un frame; no abre videos, dibuja resultados ni conoce etapas
  futuras.
- `engine/scripts/detect_video.py` coordina la fuente de OP-33, el detector y dos
  artefactos diagnósticos locales: JSONL estructurado y video anotado.
- Los pesos deben existir localmente. El uso normal no provoca descargas implícitas.

Configuración mínima utilizada:

| Parámetro | Valor |
| --- | --- |
| Modelo | YOLO11n, detección, pesos COCO oficiales |
| Archivo | `yolo11n.pt` |
| SHA-256 de pesos | `0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1` |
| Confianza mínima | `0.25` |
| IoU para NMS | `0.70` |
| Tamaño de entrada | `640` |
| Dispositivo | `cuda` |
| Filtro de clases | ninguno |

Los pesos se obtuvieron una sola vez desde los activos oficiales de Ultralytics para
la validación autorizada. Se almacenaron fuera del repositorio y no se versionaron.

## Muestra de validación

Se utilizó exclusivamente la muestra base definida por OP-18:

| Campo | Valor |
| --- | --- |
| Fuente | NVIDIA PhysicalAI SDG-Warehouse |
| Escenario | `forklift_human_nearmiss` |
| Revisión | `001e53453441935632ae` |
| Run | `run_1_seed_1288693302` |
| Cámara | `ceiling_00` |
| Archivo | `001e53453441935632ae_run_1_seed_1288693302.ceiling_00.rgb.mp4` |
| SHA-256 | `E4795E873DCBDAAA4DC3D42F533052E3C1DB62D1D3EF786C2C90DD4D7681330B` |
| Propiedades | 1920 x 1080, 30 FPS, 300 frames |

El nombre, la revisión, el run, la cámara y el SHA-256 se verificaron antes de la
inferencia. La muestra permaneció fuera del repositorio.

## Pruebas automatizadas

La suite completa de `engine/tests` se ejecutó con Python 3.12.10 y la prueba real
habilitada explícitamente mediante rutas locales en variables de entorno:

```text
Ran 13 tests in 4.979s — OK
```

El resultado incluye:

- pruebas de los tipos y sus invariantes;
- conversión de resultados mediante un modelo falso, incluida salida vacía;
- propagación de los cinco parámetros admitidos y ausencia de filtro de clases;
- rechazo de frames inválidos y de pesos inexistentes;
- integración real YOLO11n + CUDA sobre un frame de la muestra;
- las cuatro pruebas existentes de OP-33.

La prueba de integración real es opt-in: sin las variables de entorno se omite y no
descarga pesos. `pip check` informó `No broken requirements found`.

## Validación del entorno de inferencia

`check_environment.py --require-cuda` confirmó:

- Python 3.12.10 de 64 bits;
- PyTorch 2.14.0+cu130 y TorchVision 0.29.0+cu130;
- CUDA 13.0 disponible en PyTorch;
- NVIDIA GeForce RTX 3070, capacidad de cómputo 8.6;
- operación tensorial real en CUDA y fallback CPU correctos;
- OpenCV 5.0.0 y Ultralytics 8.4.146 operativos.

## Resultado de inferencia sobre 300 frames

| Métrica | Resultado |
| --- | ---: |
| Frames procesados | 300 |
| Frames con al menos una detección | 300 |
| Detecciones totales | 399 |
| `person` | 302 |
| `bus` | 73 |
| `suitcase` | 18 |
| `bench` | 4 |
| `truck` | 2 |

### Cobertura de `person`

El modelo detectó a la persona en los 300 frames. Hubo 302 detecciones porque en los
frames 80 y 82 produjo dos cajas solapadas sobre la misma persona; la inspección del
video las clasifica como duplicaciones ocasionales, no como una segunda persona.
Las confianzas de `person` estuvieron entre 0.477 y 0.926, con media 0.887.

### Cobertura de `forklift`

La cobertura explícita es **cero**. Los pesos COCO de YOLO11n no incluyen una clase
`forklift`, por lo que OP-34 no puede afirmar detección de montacargas con esta línea
base.

La inspección del video anotado mostró que el montacargas fue confundido de manera
intermitente con clases COCO:

- `bus`: 73 detecciones entre los frames 194 y 299, con interrupciones;
- `truck`: 2 detecciones, en los frames 5 y 12;
- `bench`: 4 detecciones, en los frames 2, 14, 15 y 21;
- `suitcase`: 18 detecciones en 14 frames, principalmente sobre partes del vehículo.

Estas salidas son falsos positivos o confusiones semánticas respecto del escenario.
No se reinterpretan `truck`, `bus`, `bench` ni `suitcase` como `forklift`. La ausencia
de `forklift` es una limitación real del vocabulario de los pesos y deberá abordarse
en una tarea posterior mediante una fuente de clases apropiada y su validación.

## Artefactos diagnósticos locales

Los artefactos se generaron fuera del repositorio y no contienen rutas locales en
el código ni en esta evidencia:

| Artefacto | Propiedades | SHA-256 |
| --- | --- | --- |
| `op34-yolo11n-coco-detections.jsonl` | 300 registros, 92,150 bytes | `179BF8DF91E3A76498EE9FC7858392BB483A9141A805E24DE9F4C23A6F87FD6D` |
| `op34-yolo11n-coco-annotated.mp4` | 1920 x 1080, 30 FPS, 300 frames, 4,169,903 bytes | `CBBB70BADEB76A2017BF6705E5003528EB2CCEF5AED8EB816FEE0D6CEA32F86F` |

El video anotado se produjo solo como evidencia diagnóstica de OP-34 desde el script
de ejecución. No constituye la funcionalidad formal de visualización de OP-60.

## Conclusión

La integración mínima transforma correctamente los frames de OP-33 en detecciones
estructuradas y funciona tanto mediante pruebas aisladas como con YOLO11n real en la
RTX 3070. `person` queda cubierto para la muestra evaluada. `forklift` no queda
cubierto por los pesos COCO y las etiquetas de vehículos u objetos observadas no son
equivalencias válidas. La implementación satisface el alcance técnico y el criterio
de cierre de OP-34, manteniendo documentada la brecha de cobertura del dominio.
