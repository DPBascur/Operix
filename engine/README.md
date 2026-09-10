# Motor de análisis de video

Componente de Operix Architecture v1.0 que transforma video en resultados de análisis y eventos de interés preventivo.

> La IA percibe el entorno; las reglas interpretan el contexto.

Flujo conceptual: video → detección → tracking → variables espacio-temporales → reglas configurables → evento → Backend/API → registro/histórico.

## Tecnologías y límites

- Python y OpenCV para procesamiento de video.
- YOLO11 para detección y ByteTrack para seguimiento, como selecciones iniciales y experimentales.
- Configuración recibida desde el Backend/API; resultados entregados al Backend/API.
- Sin acceso directo a PostgreSQL.
- Reglas y umbrales configurables según escenario y organización, sin valores operacionales universales fijados en código.

## Módulos internos futuros

Estos siete componentes conceptuales pertenecen al mismo motor; no son servicios independientes:

1. Procesador de video.
2. Detector de objetos.
3. Seguimiento multiobjeto.
4. Analizador espacio-temporal.
5. Gestor de configuración.
6. Motor de reglas.
7. Gestor de eventos.

## Estado

Implementación pendiente. El primer PoC previsto es video → OpenCV → YOLO11 → ByteTrack → visualización de detecciones/tracks → métricas FPS/latencia. Aportará evidencia técnica inicial para RF-01, RF-02, RF-03 y RNF-02; todavía no está implementado.

Consulte el [índice de arquitectura](../docs/architecture/README.md) para los artefactos vigentes.
