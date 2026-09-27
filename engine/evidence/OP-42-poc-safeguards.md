# OP-42 — Checklist de resguardos del PoC actual

Este checklist documenta los resguardos aplicados al PoC actual y no constituye el cierre formal de OP-42, cuyo alcance completo depende de componentes posteriores.

Alcance: clips sintéticos NVIDIA utilizados en la validación del pipeline base.
No se infiere cumplimiento de controles aún no implementados ni de OP-39.

| Aspecto | Resguardo documentado y límite | Evidencia |
| --- | --- | --- |
| Procedencia | Ambos clips provienen de `nvidia/PhysicalAI-WorldModel-Synthetic-Warehouse-Operations-Scenes`, revisión `d5b88d3abcf659f304a107f4336b71b4e2159133`. Las muestras son sintéticas; la disponibilidad pública del dataset no equivale a dominio público. | [OP-18](OP-18-data-selection.md), [OP-35](OP-35-bytetrack.md) |
| Licencia | La revisión se documentó con licencia `OpenMDW-1.1`; cualquier redistribución de clips o derivados exige revisar sus condiciones vigentes y el destino concreto. No se afirma autorización general de difusión. | [OP-18](OP-18-data-selection.md) |
| Muestra de interacción persona–montacargas | Run `001e53453441935632ae_run_1_seed_1288693302`, cámara `ceiling_00`, SHA-256 del MP4 `E4795E873DCBDAAA4DC3D42F533052E3C1DB62D1D3EF786C2C90DD4D7681330B`. | [OP-18](OP-18-data-selection.md), [OP-34](OP-34-yolo11-detection.md) |
| Muestra principal de tracking/PoC | Run `00023b5323028ab83e67_run_6_seed_1486583949`, cámara `ceiling_04`, SHA-256 del MP4 `3ABE9043EE41F898D869890E8636B804186BFAF524DAEA2E6F6831E72711F4D6`. | [OP-35](OP-35-bytetrack.md), [OP-61](OP-61-poc.md) |
| Salidas verificables | La ejecución final documentó SHA-256 del JSONL `ACAD8F3389233DE62652E590DD133ABE3B910FB91CD111BEDC00C96BA96C8DD5` y del video anotado `EA5B640009071D63D7EC756690E4437182C6DBCDD468CFE78DB0E4757735811A`; permanecen fuera del repositorio. | [OP-61](OP-61-poc.md) |
| Identidad y responsabilidad | El PoC detecta la clase `person` y emite IDs temporales de tracking. No incorpora reconocimiento facial, identificación personal ni atribución automática de responsabilidad. Un `track_id` no representa identidad civil. | [OP-35](OP-35-bytetrack.md), [OP-61](OP-61-poc.md) |
| Datos internos | La validación documentada usa las muestras sintéticas indicadas y no depende de videos internos ni de material empresarial no autorizado. No se incorporan pesos, videos, capturas ni JSONL de ejecución al repositorio. | [OP-18](OP-18-data-selection.md), [OP-61](OP-61-poc.md), [política Git](../../.gitignore) |
| Difusión | Las evidencias versionadas son descripciones técnicas y hashes, no copias audiovisuales. Antes de compartir clips, capturas o salidas visuales fuera del equipo debe revisarse la licencia y el alcance de la autorización; este checklist no concede permiso de publicación. | [OP-18](OP-18-data-selection.md), [OP-61](OP-61-poc.md) |

Quedan fuera de esta revisión los tratamientos de datos reales, controles de acceso,
retención, publicación y componentes posteriores del sistema. Se requieren análisis
y decisiones específicos antes de utilizarlos o dar por cerrado OP-42.
