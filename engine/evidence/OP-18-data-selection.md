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

## Fuentes

- Dataset: https://huggingface.co/datasets/nvidia/PhysicalAI-WorldModel-Synthetic-Warehouse-Operations-Scenes
- Licencia: https://openmdw.ai/license/1-1/
