# OP-18 — Evaluación de muestra candidata

## Identificación

- Dataset: PhysicalAI SDG-Warehouse
- Productor: NVIDIA
- Repositorio: `nvidia/PhysicalAI-WorldModel-Synthetic-Warehouse-Operations-Scenes`
- Revisión: `d5b88d3abcf659f304a107f4336b71b4e2159133`
- Escenario: `forklift_human_nearmiss` (`nearmiss` en los índices Parquet)
- Run ID: `001e53453441935632ae_run_1_seed_1288693302`
- Seed: `1288693302`
- Cámara: `ceiling_00`
- Shard: `rgb/forklift_human_nearmiss/nearmiss-rgb-00000.tar`
- Miembro: `001e53453441935632ae_run_1_seed_1288693302.ceiling_00.rgb.mp4`
- Archivo de origen registrado en el índice: `2c6e43fe1d563854d4a8_rgb.mp4`
- Licencia de la revisión: OpenMDW-1.1
- Fecha de recuperación: 2026-09-10

El MP4 se conserva en almacenamiento temporal local fuera del repositorio y no se
versiona en Git.

## Extracción y verificación

- Método: streaming secuencial del WebDataset TAR mediante una solicitud HTTP Range.
- Límite autorizado: 1 GiB por intento.
- Payload consumido antes de completar el miembro: 16.281.600 bytes.
- Tamaño exacto del MP4: 16.279.681 bytes.
- SHA-256: `e4795e873dcbdaaa4dc3d42f533052e3c1db62d1d3ef786c2c90dd4d7681330b`
- Contenedor/códec informado por OpenCV: MP4/H.264.
- Resolución: 1920 × 1080.
- FPS declarado: 30.
- Duración: 10 segundos.
- Frames declarados: 300.
- Frames procesados secuencialmente: 300.
- Apertura mediante OpenCV: satisfactoria, backend FFMPEG.

## Evaluación visual y aplicabilidad

Se inspeccionaron frames distribuidos entre 0,00 y 9,97 segundos, además de una
secuencia más densa entre 1,50 y 4,00 segundos. La persona y el montacargas son
visibles de forma continua. Entre aproximadamente 2,0 y 3,5 segundos se observa
una aproximación clara y una reacción de alejamiento de la persona, útil para una
evaluación posterior de proximidad y variables espacio-temporales.

La vista elevada mantiene ambos objetos dentro del encuadre, con oclusión baja y
sin pérdida visual prolongada. El contraste es moderado debido a la iluminación
oscura del escenario, pero las siluetas y límites principales permanecen
distinguibles. La escala de la persona es menor que la del montacargas, lo que
aporta un caso útil para comprobar sensibilidad de detección.

El clip cumple los criterios visuales para recomendarlo como muestra base del PoC
en OP-34, OP-35, OP-43, OP-60 y OP-61. La selección permanece asociada a OP-18,
que continúa abierta hasta su cierre formal.

## Comparación y justificación de la selección

La investigación de OP-16 comparó NVIDIA PhysicalAI SDG-Warehouse con Video
Dataset for Safe and Unsafe Behaviours, TOMIE y VIRAT. La matriz completa está
disponible en [OP-16-datasets.md](OP-16-datasets.md).

| Criterio decisivo | NVIDIA PhysicalAI SDG-Warehouse | Alternativas evaluadas |
| --- | --- | --- |
| Correspondencia con el escenario | Incluye explícitamente una interacción persona–montacargas en un almacén | Safe/Unsafe contiene personas y montacargas, pero sus clases de montacargas se centran en la carga; TOMIE no incluye personas; VIRAT no representa almacenes ni montacargas |
| Continuidad para tracking | Clips continuos, runs multivista y metadatos temporales reproducibles | Safe/Unsafe conserva video, pero no documenta IDs persistentes; TOMIE sí es útil para tracking de maquinaria; VIRAT ofrece tracking genérico persona–vehículo |
| Anotaciones disponibles | Bounding boxes 2D y 3D, segmentación, profundidad y parámetros de cámara en el nivel de artifacts | Safe/Unsafe publica principalmente etiquetas por clip; TOMIE tiene anotaciones industriales ricas, pero acceso y licencia pendientes; VIRAT tiene tracks bajo un acuerdo de uso específico |
| Reproducibilidad | Revisión, run ID, seed, cámara, miembro y hash identifican exactamente la muestra | Las alternativas tienen menor control de generación o presentan restricciones adicionales de acceso |
| Acceso acotado | Los índices y el streaming permitieron extraer un clip de 15,53 MiB sin materializar el shard | Safe/Unsafe permite descargar clips individuales; TOMIE no expone claramente el payload completo; VIRAT requiere aceptar su acuerdo |
| Representatividad | Alta para la interacción objetivo, con brecha simulación–realidad | Safe/Unsafe aporta el contraste real más relevante; TOMIE aporta contexto logístico real; VIRAT tiene menor ajuste al dominio |

NVIDIA queda seleccionado como muestra base provisional porque es la única alternativa
evaluada que combina en el mismo clip una persona, un montacargas, continuidad temporal,
proximidad visible, identificación reproducible y anotaciones potencialmente útiles para
evaluaciones posteriores. El clip extraído permite desarrollar y medir el pipeline común
de OP-34, OP-35, OP-43, OP-60 y OP-61 sin incorporar material empresarial.

La selección no elimina la necesidad de contraste con video real. Video Dataset for Safe
and Unsafe Behaviours queda como alternativa principal para evaluar posteriormente la
brecha de representatividad, sin requerir su descarga en esta etapa. OP-18 permanece
abierta y NVIDIA conserva el carácter de muestra base provisional.

## Fuentes

- Dataset: https://huggingface.co/datasets/nvidia/PhysicalAI-WorldModel-Synthetic-Warehouse-Operations-Scenes
- Licencia: https://openmdw.ai/license/1-1/
- Comparación OP-16: [OP-16-datasets.md](OP-16-datasets.md)
