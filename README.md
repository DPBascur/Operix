# Operix

Sistema inteligente para el análisis preventivo de riesgos operacionales mediante visión artificial.

Operix busca transformar secuencias de videovigilancia en información preventiva: detectar y seguir objetos de interés, evaluar reglas operacionales y registrar condiciones potencialmente riesgosas para su análisis posterior.

> La IA percibe el entorno; las reglas interpretan el contexto.

El aporte del Trabajo de Título consiste en diseñar, integrar y evaluar un sistema que transforma información obtenida desde video en información útil para la gestión preventiva. No se desarrolla un modelo de IA nuevo. Operix no predice ni previene accidentes, ni clasifica automáticamente todos los eventos como Near Miss.

## Estado actual

- Etapa 1 aprobada.
- Operix Architecture v1.0 cerrada.
- OP-58: preparación y estructuración del repositorio existente, conservando su historial.
- Implementación de aplicaciones y PoC pendiente; esta estructura inicial contiene documentación de responsabilidades.

## Arquitectura y alcance

Video → detección → tracking → variables espacio-temporales → reglas configurables → evento → registro/histórico.

La arquitectura define Aplicación Web, Backend/API, Motor de análisis de video y PostgreSQL. El motor entrega resultados al Backend/API; el backend gestiona la persistencia. El motor no accede directamente a PostgreSQL.

- Procesamiento de video.
- Detección y seguimiento de personas y maquinaria.
- Evaluación de reglas operacionales acotadas.
- Registro de eventos para validación y análisis.

Las reglas y umbrales operacionales son configurables y dependen del escenario y de la organización. Se utiliza el concepto de evento de interés preventivo o condición potencialmente riesgosa, sujeto a revisión humana.

## Stack aprobado

| Componente | Tecnología |
| --- | --- |
| Aplicación Web | Next.js + TypeScript |
| Backend/API | Django + Django REST Framework |
| Base de datos | PostgreSQL |
| Motor de análisis | Python |
| Procesamiento de video | OpenCV |
| Detección | YOLO11, selección inicial/experimental |
| Tracking | ByteTrack, selección inicial/experimental |
| Contenedores | Docker + Docker Compose, implementación pendiente |

Kubernetes, Redis, Celery y HAR quedan fuera del MVP inicial.

## Estructura del repositorio

| Ruta | Responsabilidad |
| --- | --- |
| [frontend/](frontend/README.md) | Aplicación Web |
| [backend/](backend/README.md) | API, configuración, consultas y persistencia |
| [engine/](engine/README.md) | Análisis de video; siete componentes conceptuales como módulos internos futuros |
| [docs/architecture/](docs/architecture/README.md) | Índice de arquitectura y artefactos vigentes |
| docs/ | Documentación académica local existente; puede incluir archivos aún sin seguimiento |
| Modelo_Trabajo_Titulo_LaTeX/ | Documentación LaTeX existente |

## Orientación técnica

El repositorio aún no incluye dependencias de aplicación, Dockerfiles, configuración Compose ni instrucciones de ejecución de un sistema funcional. Se incorporarán incrementalmente. La organización permite posteriormente un despliegue con Docker Compose conforme a DEP-01.

El primer PoC previsto comprende video → OpenCV → YOLO11 → ByteTrack → visualización de detecciones/tracks → métricas FPS/latencia. Su evidencia inicial corresponderá a RF-01, RF-02, RF-03 y RNF-02.

Antes de cambiar arquitectura o stack por una limitación de implementación, se documentarán el problema, la evidencia y la propuesta para evaluar una nueva decisión arquitectónica. Véase el [índice de arquitectura v1.0](docs/architecture/README.md).

El Excel conserva el backlog y la trazabilidad académica; GitHub Projects complementará la gestión técnica mediante Issues con títulos `[OP-XX] Descripción`, vinculados a commits y evidencias.

## Derechos reservados

Copyright © 2026 Daniel Felipe Peña Bascur. Todos los derechos reservados.

Este repositorio, su código, documentación, diseño, nombre e identidad de proyecto son material propietario y confidencial. No se autoriza su copia, modificación, distribución, uso comercial ni reutilización, total o parcial, sin autorización previa y por escrito del titular.
