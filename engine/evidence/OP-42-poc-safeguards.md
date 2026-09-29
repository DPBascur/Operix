# OP-42 — Aplicar resguardos de evidencia y alcance del PoC

**Estado académico:** completada en Backlog V0.10.1 para el alcance acotado de
Etapa 2 documentado aquí. Este cierre comprende la evidencia y los resguardos
del PoC con clips públicos y sintéticos; no equivale a controles implementados
para video industrial real ni para eventos persistidos.

## A. Procedencia de datos

| Elemento | Registro verificable | Fuente |
| --- | --- | --- |
| Dataset y proveedor | NVIDIA PhysicalAI WorldModel Synthetic Warehouse Operations Scenes, repositorio `nvidia/PhysicalAI-WorldModel-Synthetic-Warehouse-Operations-Scenes`. Datos sintéticos; disponibilidad pública no significa dominio público. | [OP-18](OP-18-data-selection.md) |
| Revisión y licencia documentada | Revisión `d5b88d3abcf659f304a107f4336b71b4e2159133`; licencia documentada para esa revisión: `OpenMDW-1.1`. La difusión de clips o derivados requiere revisar sus condiciones y el destino concreto. | [OP-18](OP-18-data-selection.md) |
| Interacción persona–montacargas | Escenario `forklift_human_nearmiss`, run `001e53453441935632ae_run_1_seed_1288693302`, cámara `ceiling_00`, archivo `001e53453441935632ae_run_1_seed_1288693302.ceiling_00.rgb.mp4`, 300 frames. SHA-256 del MP4: `E4795E873DCBDAAA4DC3D42F533052E3C1DB62D1D3EF786C2C90DD4D7681330B`. | [OP-18](OP-18-data-selection.md), [OP-34](OP-34-yolo11-detection.md) |
| Tracking y PoC integrado | Escenario `warehouse_fire`, run `00023b5323028ab83e67_run_6_seed_1486583949`, cámara `ceiling_04`, archivo `00023b5323028ab83e67_run_6_seed_1486583949.ceiling_04.rgb.mp4`, 277 frames. SHA-256 del MP4: `3ABE9043EE41F898D869890E8636B804186BFAF524DAEA2E6F6831E72711F4D6`. | [OP-35](OP-35-bytetrack.md), [OP-61](OP-61-poc.md) |
| Salidas de la ejecución final | SHA-256 del JSONL de tracks: `ACAD8F3389233DE62652E590DD133ABE3B910FB91CD111BEDC00C96BA96C8DD5`; permanece fuera de Git. El video anotado, SHA-256 `EA5B640009071D63D7EC756690E4437182C6DBCDD468CFE78DB0E4757735811A`, se incorpora como única salida visual de demostración. | [OP-61](OP-61-poc.md), [NOTICE](../../third_party/nvidia-warehouse-dataset/NOTICE.md) |

## B. Identidad y privacidad

- El PoC no implementa reconocimiento facial, biometría ni identificación
  personal. `person` es una clase de detección y `track_id` identifica
  temporalmente un track dentro de una sesión, no a una persona real.
- Las muestras sintéticas no acreditan por sí solas medidas suficientes para
  un despliegue sobre CCTV real. Ese tratamiento requeriría evaluación propia.

## C. Alcance preventivo

- No se asigna responsabilidad individual ni se aplican sanciones automáticamente.
- El PoC no clasifica automáticamente infracciones ni Near Miss. La
  interpretación de una condición depende del contexto operacional y de
  revisión humana.
- En OP-38, `EventCandidate` indica únicamente que se cumplió una regla
  configurada. No equivale a accidente, Near Miss, infracción o responsabilidad.
  [OP-38](OP-38-rules.md) documenta el umbral experimental y su alcance.

## D. Datos internos

- La validación documentada no depende de videos ni datasets internos de una
  empresa. No se presupone autorización para usarlos o difundirlos.
- Cualquier uso futuro de material interno requiere autorización específica y
  evaluación adicional de privacidad, acceso y finalidad antes de incorporarlo.
  Esa validación adicional no es una dependencia para reproducir el PoC actual.

## E. Evidencia y difusión

- Se versionan configuración, código, pruebas, evidencias técnicas y hashes para
  trazabilidad. Como excepción acotada a la [política Git](../../.gitignore),
  se incluyen los dos clips sintéticos verificados y un resultado anotado en
  [`assets/demo`](../../assets/demo/), con licencia y atribución en el
  [NOTICE](../../third_party/nvidia-warehouse-dataset/NOTICE.md). Pesos,
  otros videos, capturas, JSONL de ejecución y logs permanecen fuera de Git.
- No se deben publicar material confidencial, secretos, credenciales ni rutas
  personales. La existencia de un hash no autoriza redistribuir el artefacto.
- Antes de difundir clips, capturas o derivados debe verificarse la licencia
  aplicable y el permiso concreto. Este checklist no concede tal autorización.

## Límite del cierre académico

El cierre de OP-42 en V0.10.1 se refiere a procedencia, revisión y licencia del
dataset, hashes, trazabilidad, atribución, material público/sintético, identidad
temporal de `track_id`, ausencia de biometría y de decisiones automáticas sobre
responsabilidad, sanción o Near Miss, y resguardos de los tres clips de demo.

No se han implementado persistencia de eventos, control de acceso,
roles/permisos, retención, consulta histórica persistente ni gestión de eventos
almacenados. Esas materias y cualquier evaluación de CCTV industrial real
pertenecen a etapas posteriores; no son condiciones retroactivas del cierre de
OP-42 en Etapa 2.
