# Operix

Sistema inteligente para el análisis preventivo de riesgos operacionales mediante visión artificial.

Operix busca transformar secuencias de videovigilancia en información preventiva: detectar y seguir objetos de interés, evaluar reglas operacionales y registrar condiciones potencialmente riesgosas para su análisis posterior.

> La IA percibe el entorno; las reglas interpretan el contexto.

El aporte del Trabajo de Título consiste en diseñar, integrar y evaluar un sistema que transforma información obtenida desde video en información útil para la gestión preventiva. No se desarrolla un modelo de IA nuevo. Operix no predice ni previene accidentes, ni clasifica automáticamente todos los eventos como Near Miss.

## Estado actual

- Etapa 1 aprobada.
- Operix Architecture v1.0 cerrada.
- OP-58: preparación y estructuración del repositorio existente, conservando su historial.
- Pipeline base del Motor implementado y validado: OP-33, OP-34, OP-35, OP-60 y OP-43.
- OP-61: ejecución integrada y consolidación documental completadas y aprobadas para cierre formal.
- Reglas, eventos, persistencia, Backend/API y Aplicación Web permanecen pendientes de implementación.

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

## Clonación

El repositorio es privado; se requiere acceso autorizado a `DPBascur/Operix`.

```powershell
git clone https://github.com/DPBascur/Operix.git
cd Operix
git switch dev
```

`main` conserva el hito estable `v0.1.0`; `dev` es la rama habitual de desarrollo.
Los diagramas y ADR completos de arquitectura no se incluyen en el clon: el
[índice de arquitectura](docs/architecture/README.md) identifica los once
artefactos y distingue las referencias externas de los archivos versionados.

## Estructura del repositorio

| Ruta | Responsabilidad |
| --- | --- |
| [frontend/](frontend/README.md) | Aplicación Web |
| [backend/](backend/README.md) | API, configuración, consultas y persistencia |
| [engine/](engine/README.md) | Pipeline base ejecutable de video, detección, tracking y visualización; componentes operacionales posteriores pendientes |
| [docs/architecture/](docs/architecture/README.md) | Índice de arquitectura y artefactos vigentes |
| docs/ | Documentación académica local existente; puede incluir archivos aún sin seguimiento |
| Modelo_Trabajo_Titulo_LaTeX/ | Documentación LaTeX existente |

## Orientación técnica

El Motor dispone de entorno reproducible Windows/CUDA, scripts de ejecución y pruebas. El sistema completo, los Dockerfiles y la configuración Compose siguen pendientes. La organización permite posteriormente un despliegue con Docker Compose conforme a DEP-01.

El PoC técnico ejecutado comprende video → OpenCV → YOLO11 → ByteTrack → visualización, con métricas del benchmark independiente de OP-43. La [evidencia consolidada de OP-61](engine/evidence/OP-61-poc.md) registra configuración, entorno, hashes, resultados y limitaciones como evidencia inicial de RF-01, RF-02, RF-03 y RNF-02.

La validación principal filtra `person`. Los pesos COCO no contienen `forklift` y no demuestran tracking fiable de maquinaria. Los resultados proceden de muestras sintéticas acotadas; no acreditan funcionamiento universal o sostenido en tiempo real ni validación completa de Operix.

Antes de cambiar arquitectura o stack por una limitación de implementación, se documentarán el problema, la evidencia y la propuesta para evaluar una nueva decisión arquitectónica. Véase el [índice de arquitectura v1.0](docs/architecture/README.md).

El Excel conserva el backlog y la trazabilidad académica; GitHub Projects complementará la gestión técnica mediante Issues con títulos `[OP-XX] Descripción`, vinculados a commits y evidencias.

## Derechos reservados

Copyright © 2026 Daniel Felipe Peña Bascur. Todos los derechos reservados.

Este repositorio, su código, documentación, diseño, nombre e identidad de proyecto son material propietario y confidencial. No se autoriza su copia, modificación, distribución, uso comercial ni reutilización, total o parcial, sin autorización previa y por escrito del titular.
