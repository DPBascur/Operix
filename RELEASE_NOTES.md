# Notas de release

## v0.2.0 — MVP integrado / cierre técnico de Etapa 3

**Candidato validado, no publicado.** El gate final está aprobado; quedan pendientes
la promoción de main y la creación del tag. Estas notas no crean
un GitHub Release ni cambian las versiones declaradas de los paquetes.

### Alcance

- Pipeline integrado de video, percepción dual, ByteTrack por clase, variables
  espacio-temporales y reglas configurables.
- YOLO11m COCO para PERSON, seleccionado por equilibrio calidad/costo sobre datos
  de desarrollo para análisis diferido; FORKLIFT specialist v2 congelado.
- Zonas, zone_dwell y person_forklift_proximity; distancia entre segmentos
  inferiores bajo `person_equipment_nearest_ground_edges_v1`.
- Eventos PostgreSQL, evidencia PNG, snapshots con identidad/SHA de modelos,
  journal y reenvíos acotados. Video anotado H.264 temporal de sesión.
- Histórico, filtros, frecuencias/indicadores y detalle con evidencia, mediciones
  y trazabilidad técnica, separados del dashboard ilustrativo.
- Hardening de sesiones, integridad/cadencia de video, navegación y respuestas
  obsoletas; correcciones del replay multiclase y entradas numéricas extremas.
- Ruta nativa y Docker Compose CPU/GPU, con pesos externos read-only.
- Geometría de botones compartida entre light/dark, conservando colores y estados.
- [Captura actual](assets/demo/v0.2.0/README.md) del flujo real como único asset
  visual principal; el video actual de QA permanece fuera de Git. El
  [PoC v0.1.0](assets/demo/README.md) permanece identificado como histórico.

### Evidencia y regresión

La base de preparación de assets es `21b9b05704c2a8560d08f21a5a915b2b0a58cc91`.
El cierre P1 registró Motor 425 PASS + 2 SKIP, Backend 127/127, Frontend 37/37,
browser 1/1, lint/typecheck/build y checks Django/migraciones/dependencias aprobados.
No se convierten pruebas fixture en evaluación de percepción ni se atribuye el
benchmark histórico OP-43 al pipeline actual.

La [auditoría](engine/evidence/ETAPA4-TECHNICAL-AUDIT.md) conserva decisiones,
resultados y el gate final. La selección de PERSON **no constituye validación
independiente final**. No se reutilizan holdouts para preparar esta demo.

### Límites conocidos

- Pendientes validación externa/contextual experta y operacional final realista;
  v0.2.0 no representa cierre académico final ni sistema industrial terminado.
- Distancia normalizada en imagen, sin metros ni umbral universal de seguridad.
  Evento significa condición configurada satisfecha; requiere revisión humana.
- Gaps/cambios de ID pueden fragmentar episodios. No hay supresión automática de
  operador ni ground truth MOT suficiente para garantías de continuidad.
- MOBILE_EQUIPMENT/TRUCK y PERSON v2 diferidos. Análisis de video diferido, sin
  garantía universal de tiempo real.
- API local sin autenticación empresarial y retención manual. P2 conocidos de
  PNG, recuperación de journals truncados, deadlines, contexto de filtros y
  mantenibilidad permanecen abiertos según auditoría.

### Versionado pendiente del release final

No existe una única versión global compartida entre componentes:

- `engine/pyproject.toml`: versión del paquete Motor, fuente de metadata de build.
- `engine/src/operix_engine/__init__.py`: constante pública que debe concordar.
- `frontend/package.json`: versión propia de la aplicación Web.

Las tres fuentes activas declaran **0.2.0** como versión candidata. La promoción
a main y el tag permanecen pendientes de autorización tras aprobar el gate final.
La ruta `/api/v1` es versión del contrato API y no cambia por este release.
El tag anotado v0.1.0 conserva su objetivo histórico.
