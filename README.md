# Operix

Sistema inteligente para el análisis preventivo de riesgos operacionales mediante visión artificial.

Operix busca transformar secuencias de video en información para revisión preventiva: detectar y seguir objetos de interés, calcular variables descriptivas y evaluar reglas operacionales. El registro persistente de eventos es una etapa futura.

> La IA percibe el entorno; las reglas interpretan el contexto.

El aporte del Trabajo de Título consiste en diseñar, integrar y evaluar un sistema que transforma información obtenida desde video en información útil para la gestión preventiva. No se desarrolla un modelo de IA nuevo. Operix no predice ni previene accidentes, ni clasifica automáticamente todos los eventos como Near Miss.

## Estado actual

- Etapa 1 aprobada.
- Operix Architecture v1.0 cerrada.
- OP-58: preparación y estructuración del repositorio existente, conservando su historial.
- Pipeline base del Motor implementado y validado: OP-33, OP-34, OP-35, OP-60 y OP-43.
- OP-61: ejecución integrada y consolidación documental completadas.
- OP-30 (configuración), OP-36 (pertenencia a zonas), OP-37 (variables espacio-temporales) y OP-38 (primera regla configurable) están completadas.
- OP-42: resguardos de evidencia y alcance del PoC completados académicamente en V0.10.1 para Etapa 2.
- Persistencia de eventos, Backend/API y Aplicación Web permanecen pendientes.

## Arquitectura y alcance

Video → detección → tracking → variables espacio-temporales → reglas configurables → `EventCandidate` en memoria. La persistencia e histórico pertenecen a etapas posteriores.

La arquitectura define Aplicación Web, Backend/API, Motor de análisis de video y PostgreSQL. En el sistema futuro, el Motor entregará resultados al Backend/API y este gestionará la persistencia. Esa integración aún no está implementada; el Motor no accede directamente a PostgreSQL.

- Procesamiento de video.
- Detección y seguimiento experimental de `person`; cobertura de maquinaria pendiente de pesos/clases apropiados.
- Evaluación inicial de una regla operacional configurable (`zone_dwell`).
- Emisión de candidatos transitorios; todavía no hay registro persistente de eventos.

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

Para clonar el repositorio se requiere acceso conforme a su visibilidad vigente en GitHub. Esta guía no presupone una visibilidad permanente.

```powershell
git clone https://github.com/DPBascur/Operix.git
cd Operix
git switch dev
```

`main` conserva el hito estable `v0.1.0`; `dev` es la rama habitual de desarrollo.
Los seis diagramas y los cinco ADR de la arquitectura base v1.0 están
disponibles en [docs/architecture/](docs/architecture/README.md), junto con
la exportación completa de IcePanel. Documentan el diseño aprobado, no la
implementación completa del sistema.

## Estructura del repositorio

| Ruta | Responsabilidad |
| --- | --- |
| [frontend/](frontend/README.md) | Aplicación Web |
| [backend/](backend/README.md) | API, configuración, consultas y persistencia |
| [engine/](engine/README.md) | Pipeline base ejecutable y módulos operacionales de configuración, zonas, variables espacio-temporales y evaluación inicial de reglas; persistencia pendiente |
| [docs/architecture/](docs/architecture/README.md) | Seis diagramas, cinco ADR y exportación completa de IcePanel de la arquitectura v1.0 |
| [assets/demo/](assets/demo/README.md) | Dos entradas sintéticas y un video anotado para revisión |
| [third_party/](third_party/nvidia-warehouse-dataset/NOTICE.md) | Procedencia, atribución y licencia de los clips NVIDIA |
| [engine/evidence/](engine/evidence/) | Evidencias técnicas y resultados versionables |

## Instalación, pruebas y demostración

Se requiere Python 3.12 x64. La [guía del Motor](engine/README.md#entorno-local)
separa la instalación Windows/NVIDIA-CUDA de la opción CPU y explica el lock
reproducible. Tras instalar el entorno, desde la raíz del clon:

```powershell
.\engine\.venv\Scripts\python.exe -m pip check
.\engine\.venv\Scripts\python.exe .\engine\scripts\check_environment.py
.\engine\.venv\Scripts\python.exe -m unittest discover -s .\engine\tests -v
```

En un equipo NVIDIA compatible, añadir `--require-cuda` al verificador. Las
pruebas de inferencia real son optativas y requieren pesos y muestras locales
indicados mediante variables de entorno; sin ellos se omiten. Para reproducir
la salida visual con una entrada incluida, seguir la [guía de demo](assets/demo/README.md).
Los pesos `yolo11n.pt` no se distribuyen en este repositorio.

## Orientación técnica

El Motor dispone de entorno reproducible Windows/CUDA, scripts de ejecución y pruebas. El sistema completo, los Dockerfiles y la configuración Compose siguen pendientes. La organización permite posteriormente un despliegue con Docker Compose conforme a DEP-01.

El PoC técnico ejecutado comprende video → OpenCV → YOLO11 → ByteTrack → visualización, con métricas del benchmark independiente de OP-43. La [evidencia consolidada de OP-61](engine/evidence/OP-61-poc.md) registra configuración, entorno, hashes, resultados y limitaciones como evidencia inicial de RF-01, RF-02, RF-03 y RNF-02.

Después de ese hito, el desarrollo incorpora configuración de zonas y reglas (OP-30), pertenencia geométrica (OP-36), variables espacio-temporales (OP-37) y evaluación inicial `zone_dwell` (OP-38). Los candidatos emitidos en memoria no son eventos persistidos ni una clasificación automática de riesgo.

La validación principal filtra `person`. Los pesos COCO no contienen `forklift` y no demuestran tracking fiable de maquinaria. Los resultados proceden de muestras sintéticas acotadas; no acreditan funcionamiento universal o sostenido en tiempo real ni validación completa de Operix.

## Datos de demostración

### Interacción persona–montacargas

https://github.com/user-attachments/assets/93648968-ae9e-4c66-aef2-c04be7ff2bae

### Procesamiento de una muestra

#### Entrada

https://github.com/user-attachments/assets/82707306-f3de-40d4-b8fd-fb3f3c292fee

#### Resultado de Operix

https://github.com/user-attachments/assets/1271a029-4057-421e-a13b-72baf02d08e0




Operix se evaluó con dos clips sintéticos del dataset NVIDIA PhysicalAI WorldModel
Synthetic Warehouse Operations Scenes. [La muestra persona–montacargas](assets/demo/forklift_human_nearmiss_ceiling00.mp4)
se usó para revisar detección y su limitación de cobertura de `forklift` (OP-34).
[La muestra de almacén](assets/demo/warehouse_fire_ceiling04.mp4) permitió revisar
tracking, visualización y el PoC integrado (OP-35/60/61). Se incluye también
[el resultado anotado](assets/demo/warehouse_fire_ceiling04_operix_annotated.mp4)
de esa segunda muestra para comparar entrada y salida visual. Son datos de terceros;
su procedencia, hashes, atribución y [licencia OpenMDW-1.1](third_party/nvidia-warehouse-dataset/NOTICE.md)
están documentados en el NOTICE y en la [guía de demo](assets/demo/README.md). No representan video de una empresa ni
validación industrial.

Antes de cambiar arquitectura o stack por una limitación de implementación, se documentarán el problema, la evidencia y la propuesta para evaluar una nueva decisión arquitectónica. Véase el [índice de arquitectura v1.0](docs/architecture/README.md).

El Excel conserva el backlog y la trazabilidad académica; GitHub Projects complementa la gestión técnica mediante Issues con títulos `[OP-XX] Descripción`, vinculados a commits y evidencias.

## Licencia

Copyright (C) 2026 Daniel Felipe Peña Bascur.

El código fuente propio de la versión académica de Operix se distribuye bajo
**GNU Affero General Public License v3.0 or later** (`AGPL-3.0-or-later`).
Daniel Felipe Peña Bascur conserva la titularidad de su código original; los
términos completos de la licencia están en [LICENSE](LICENSE).

Los materiales de terceros conservan sus propias licencias y condiciones; no
quedan relicenciados por la licencia del código Operix. Consultar los
[avisos de terceros](THIRD_PARTY_NOTICES.md).

Los clips NVIDIA incluidos en `assets/demo/` no son propiedad de Operix y
no se relicencian bajo AGPL-3.0-or-later. Conservan la licencia OpenMDW-1.1 y
la atribución indicadas en su
[NOTICE](third_party/nvidia-warehouse-dataset/NOTICE.md).
