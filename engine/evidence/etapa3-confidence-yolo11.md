# Etapa 3 — Experimento controlado del umbral de confianza YOLO11

## Pregunta y alcance

¿Cómo cambia el pipeline de detección `person` → ByteTrack → permanencia en zona → evento al variar **únicamente** `confidence` de YOLO11n entre 0,10, 0,25, 0,40 y 0,50? La hipótesis exploratoria es que un umbral mayor reducirá detecciones, pero también puede interrumpir tracks y cambiar los candidatos de evento. No se modifica el valor predeterminado del Motor.

Experimento local del 14-10-2026 sobre un solo video sintético. No es una prueba de precisión, seguridad operacional ni desempeño industrial. La fecha `2026-10-14T17:00:00Z` usada en `--recording-start-at` es un **ancla de análisis**, no una fecha de captura acreditada.

## Fuente, controles y entorno

- Video: `warehouse_fire_ceiling04.mp4` de NVIDIA PhysicalAI WorldModel Synthetic Warehouse Operations Scenes, licencia OpenMDW-1.1; SHA-256 `3ABE9043EE41F898D869890E8636B804186BFAF524DAEA2E6F6831E72711F4D6`; 277 frames, 1920×1080, 30 FPS, 9,233 s.
- Pesos oficiales `yolo11n.pt` externos a Git: SHA-256 `0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1`. YOLO11n-COCO, `imgsz=640`, IoU `0,70`, dispositivo CUDA, filtro posterior `person`.
- Configuración operacional sin cambios: `desktop-zone-dwell.json`, SHA-256 `4CDB60006900F7547C1699DD5AFE05399607ECA2735E178E42ED7DB535A18B27`; vista `ceiling_04`, zona `area_transito_demo` con polígono normalizado `[[0.03,0.60],[0.97,0.60],[0.97,0.98],[0.03,0.98]]`, regla `demo_zone_dwell` v1 y `min_duration_s=2,0` (experimental, no umbral de seguridad).
- ByteTrack sin cambios: high `0,25`, low `0,10`, new `0,25`, buffer `30`, match `0,80`, `fuse_score=true`. Trayectorias: 60 puntos; retención: 30 frames.
- Equipo: Windows 10 x64, AMD Ryzen 5 5500, 31,89 GiB RAM, NVIDIA GeForce RTX 3070 (8 GiB VRAM), driver 616.92. Python 3.12.10, PyTorch 2.14.0+cu130, CUDA 13.0, OpenCV 5.0.0, Ultralytics 8.4.146, `lap` 0.5.12. `check_environment.py --require-cuda` confirmó operación tensorial en GPU.
- API Django/PostgreSQL local saludable. No se modificaron pesos, drivers, dependencias, detector, tracker, zona, regla ni datos fuente.

Se reutilizó `process_video_events.py` para cada umbral con hashes esperados, misma configuración, misma ancla temporal y sin `--analysis-run-id` explícito. El script deriva así un UUID lógico de hashes de video, pesos y configuración más ajustes del detector/tracker. Se empleó `track_video.py` **solo como diagnóstico secundario** para obtener JSONL por frame, resúmenes de continuidad y videos anotados fuera del repositorio; sus tiempos no se mezclan con los del pipeline de eventos. No se creó un orquestador nuevo.

## Resultados del pipeline integrado

El tiempo comienza después de cargar el detector y comprende lectura, inferencia, tracking, análisis, creación de PNG cuando hay candidato y publicación HTTP. FPS = 277 / tiempo. La primera corrida de 0,10 ya encontraba eventos de una prueba previa; las otras tres crearon sus filas nuevas. Por tanto, los tiempos son exploratorios y **no constituyen un benchmark aislado ni una comparación causal de FPS entre umbrales**.

| `confidence` | Frames | Tiempo s | FPS efectivo | Detecciones `person` | Observaciones tracking | IDs temporales | Candidatos/eventos lógicos | Respuesta de publicación | Observación |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 0,10 | 277 | 11,790 | 23,494 | 1.088 | 644 | 8 | 4 | 4 duplicados lógicos | Baseline; conserva dos eventos en frame 60. |
| 0,25 | 277 | 12,000 | 23,083 | 668 | 632 | 8 | 3 | 3 nuevos | No se produjo el evento de track 2 en frame 60. |
| 0,40 | 277 | 11,678 | 23,720 | 605 | 592 | 6 | 3 | 3 nuevos | Cambian tracks y frames de eventos tardíos. |
| 0,50 | 277 | 12,353 | 22,423 | 541 | 537 | 4 | 4 | 4 nuevos | Menos observaciones, más huecos; dos eventos del mismo ID 1. |

Todas las corridas terminaron correctamente, procesaron 277/277 frames y publicaron o reconocieron por idempotencia todos sus candidatos. No se observaron errores o warnings del pipeline. La API contenía 12 eventos antes de este experimento y 22 después: 3 + 3 + 4 filas nuevas; la ejecución de 0,10 y los reintentos no añadieron filas.

| Confianza | `analysis_run_id` derivado | Eventos: frame/track |
| ---: | --- | --- |
| 0,10 | `6ba120ca-43ef-5e50-b5a2-af1fd44912e0` | 60/1, 60/2, 134/13, 201/31 |
| 0,25 | `8b514bb4-ff2a-53e3-b4ba-0e46eac07429` | 60/1, 134/13, 201/31 |
| 0,40 | `23b0d804-98ad-5c5e-8194-2191aa45f396` | 60/1, 140/7, 231/13 |
| 0,50 | `d7a64ff9-c7b5-59bb-a416-5b276dac6123` | 65/1, 168/1, 230/4, 238/5 |

Los IDs de track son locales a cada corrida; el mismo número en dos configuraciones **no acredita la misma identidad física**. El conteo 4 a 0,50 tampoco significa mejor detección: algunos candidatos anteriores no se produjeron y otros surgieron después. Sin verdad terreno, no se etiquetan como falsos positivos o falsos negativos.

## Continuidad observable del tracking

El resumen siguiente procede del diagnóstico `track_video.py` con el mismo video, pesos, umbrales y ByteTrack. Un «hueco» es un tramo sin observación dentro del primer y último frame de un mismo `track_id`; una reaparición no demuestra recuperación de la misma persona. No hay correspondencia de identidades ni métricas MOT formales.

| Confianza | IDs | Observaciones | Episodios de hueco | Frames ausentes dentro de spans | Tracks de hasta 5 observaciones | Ejemplos de tracks prolongados |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 0,10 | 8 | 644 | 4 | 15 | 1 | ID 1: 218 frames sin huecos; ID 31: 136 sin huecos. |
| 0,25 | 8 | 632 | 6 | 18 | 2 | ID 1: 217 frames y un hueco; ID 31: 136 sin huecos. |
| 0,40 | 6 | 592 | 11 | 18 | 2 | ID 1: 213 frames y dos huecos; ID 7: 187 y dos huecos. |
| 0,50 | 4 | 537 | 15 | 53 | 0 | ID 1: 202 frames y seis huecos; ID 5: 111 y tres huecos, incluido uno de 17 frames. |

En 0,10 se observa un track de dos frames y en 0,25 uno de un frame; la menor cantidad de tracks breves en 0,50 coexiste con más discontinuidades de tracks largos. En 0,25 el track 2 tiene un hueco en frame 51 y no genera el candidato de frame 60 que sí aparece a 0,10. Es una explicación **compatible** con la interrupción de permanencia, no una atribución causal demostrada. La fragmentación probable entre tracks y las salidas/entradas siguen siendo observaciones visuales, no ID switches confirmados.

## Repetibilidad e idempotencia

Se repitieron 0,25, 0,40 y 0,50 sin cambiar insumos ni fecha ancla. Cada repetición conservó su `analysis_run_id`, los 277 frames, detecciones, observaciones, IDs, frames/tracks de candidatos y hashes de PNG. La API respondió HTTP 200 para los 3, 3 y 4 eventos respectivos, creó **cero** filas nuevas y mantuvo los mismos Event IDs; el total quedó en 22. La corrida de 0,10 también obtuvo cuatro duplicados lógicos de su identidad preexistente.

| Confianza repetida | Tiempo s | FPS | Nuevos | Duplicados lógicos |
| ---: | ---: | ---: | ---: | ---: |
| 0,25 | 11,833 | 23,410 | 0 | 3 |
| 0,40 | 9,206 | 30,090 | 0 | 3 |
| 0,50 | 9,088 | 30,481 | 0 | 4 |

La variación de tiempos entre primeras corridas y reintentos muestra la influencia de estado de API, cachés y condiciones de ejecución; no se infiere un efecto de velocidad atribuible únicamente a `confidence` ni se afirma funcionamiento sostenido en tiempo real. La identidad lógica distingue los cuatro umbrales; la idempotencia depende de que frames y IDs de track vuelvan a coincidir.

## Evidencia visual recuperable

Se inspeccionaron PNG de frames reales anotados, almacenados como medios locales del Backend **fuera de Git**. La tabla da identificador y hash para recuperarlos por `GET /api/v1/events/{id}/evidence/`; no se incorporan PNG ni rutas personales al repositorio.

| Configuración / frame | Event ID | SHA-256 PNG | Observación visual |
| --- | --- | --- | --- |
| 0,25 / 60 | `38b0de70-c855-4a06-a181-243ede7d52cb` | `52972FFE38EBA393F51697615E9C1B753867628931FE45C65408D8F4BD9D9387` | Dos personas visibles; solo una corresponde al candidato publicado en esta configuración. |
| 0,40 / 140 | `2652598b-28e2-4110-91ac-2d653d644e64` | `660C0E8C206311967BEAE66518C997359A99C5C0C968864E6BC0FC400FB29628` | Se observan personas próximas con tracks distintos; candidato de frame 140. |
| 0,50 / 65 | `cd6050d0-9734-482f-90cc-b3da5ab506e5` | `F48683BDAF03016E4458F3AB2BBD8AEC677C2B5F2B7E79066D0EC2DC0464AE28` | Dos personas visibles; el primer candidato llega cinco frames después que con umbrales menores. |
| 0,50 / 168 | `bf6f50e0-79ee-46a9-b440-7f9ff5e968e1` | `74CE50D3213BD21B65099B0B307BF1A92543BF0A5BFB7C7892982CEF49FDA198` | Dos anotaciones visibles en zona; nuevo candidato del ID 1. |

Los JSONL por frame y MP4 diagnósticos permanecen en almacenamiento local externo al repositorio. Sus identificadores de integridad son:

| Confianza | JSONL y SHA-256 | MP4 y SHA-256 |
| ---: | --- | --- |
| 0,10 | `tracking-0.10.jsonl` — `ACAD8F3389233DE62652E590DD133ABE3B910FB91CD111BEDC00C96BA96C8DD5` | `tracking-0.10.mp4` — `EA5B640009071D63D7EC756690E4437182C6DBCDD468CFE78DB0E4757735811A` |
| 0,25 | `tracking-0.25.jsonl` — `29DCAC17E9301C571CAF282217B2142405147155658F3929C45D0A524241D483` | `tracking-0.25.mp4` — `871EF03D40B274D7EEF4A857CD13D527430D41B604AB88FE6E34BD31891010A0` |
| 0,40 | `tracking-0.40.jsonl` — `384921E7B2F87033A6A26752E3577A2F92713E3F5D23C8C4DE94A3190B1CC407` | `tracking-0.40.mp4` — `4198CE972ED0F9EB4F96413B2512503F69BF844BB99622A1511C0FD879B7AFEB` |
| 0,50 | `tracking-0.50.jsonl` — `03162C2B188846FD43937F0A4056184D953CA2377DDD325F1A0C997A648D5D6F` | `tracking-0.50.mp4` — `2FBADDF6F2484DE32CBDE724A56211D96536FF9AA6A9BAD5D2EDA9498CC0F8F9` |

No se versionan medios, bases de datos, pesos ni resultados voluminosos. Los archivos permiten revisar entradas/salidas, trayectorias y posibles fragmentaciones con más detalle; las observaciones tabuladas no equivalen a un etiquetado manual de identidad.

## Análisis y decisión provisional

Al subir `confidence` de 0,10 a 0,50, las detecciones `person` bajan de 1.088 a 541 y las observaciones de tracking de 644 a 537. El número de IDs baja de 8 a 4, pero los episodios de hueco aumentan de 4 a 15. El evento de frame 60/track 2 deja de producirse desde 0,25; en 0,40 y 0,50 cambian también tiempos y tracks de otros candidatos. La cantidad de eventos **no es monótona** (4, 3, 3, 4): el umbral mayor no equivale a más o menos «riesgo».

Para **esta escena y esta regla de permanencia**, se recomienda conservar provisionalmente `confidence=0,10` como baseline: mantiene más observaciones, menos huecos en tracks largos y los dos candidatos del frame 60 para las dos personas visibles. No se modifica el default. Esta elección prioriza continuidad útil y cobertura exploratoria, no precisión formal; también conserva detecciones/tracks que podrían ser espurios. Un estudio posterior con etiquetas y varios escenarios podría justificar otro umbral.

## Limitaciones

Una sola escena sintética, una cámara y una zona amplia de demostración; sin ground truth de cajas, identidades ni eventos. No se puede medir precisión, recall, IDF1, MOTA, falsos positivos o falsos negativos ni inferir seguridad operacional. Los IDs temporales no identifican personas. COCO no incluye la clase `forklift`; esta prueba filtra `person` y no evalúa maquinaria. Los resultados dependen de este video, hardware, versiones, regla y ancla de análisis; no se generalizan a CCTV industrial real. El tiempo integrado incluye HTTP y PNG de candidatos, pero excluye carga inicial del modelo; no sustituye el benchmark OP-43. No se cambiaron reglas, zonas, frontend, backend, pesos ni parámetros predeterminados.
