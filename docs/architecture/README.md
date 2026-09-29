# Arquitectura de Operix v1.0

La línea base **Operix Architecture v1.0** se cerró el 10/09/2026. Los diagramas siguientes documentan el **diseño arquitectónico**; su presencia aquí no significa que todos los componentes o flujos representados estén implementados. Para distinguir el estado del software, consultar el [README principal](../../README.md).

## Diagramas

Los seis diagramas están disponibles en este directorio. Para los tres C4, el PNG facilita la visualización en GitHub y el PDF conserva la página documental extraída sin redibujar de la [exportación completa de IcePanel](architecture-v1.0-icepanel-export.pdf). Esta última conserva también el índice y las descripciones de actores, sistemas y componentes.

| ID | Artefacto | Visualización | Alternativa documental |
| --- | --- | --- | --- |
| C4-01 | Contexto | [PNG](C4-01-contexto.png) | [PDF](C4-01-contexto.pdf), página 2 del original |
| C4-02 | Contenedores | [PNG](C4-02-contenedores.png) | [PDF](C4-02-contenedores.pdf), página 3 del original |
| C4-03 | Componentes del motor | [PNG](C4-03-componentes-motor.png) | [PDF](C4-03-componentes-motor.pdf), página 4 del original |
| SEQ-01 | Flujo de procesamiento de un evento preventivo | [PNG](SEQ-01-flujo-evento.png) | — |
| ERD-01 | Modelo de datos | [PNG](ERD-01-modelo-datos.png) | — |
| DEP-01 | Diagrama de despliegue | [PNG](DEP-01-despliegue.png) | — |

## Decisiones de arquitectura

Los cinco ADR aprobados forman parte de la arquitectura base v1.0. Sus textos originales exportados de IcePanel se encuentran en:

| ID | Decisión documentada |
| --- | --- |
| ADR-01 | [Arquitectura híbrida y modular de Operix](adr/ADR-01.md) |
| ADR-02 | [Separación del motor de análisis y Backend](adr/ADR-02.md) |
| ADR-03 | [Persistencia desacoplada del motor](adr/ADR-03.md) |
| ADR-04 | [Selección del stack tecnológico de Operix](adr/ADR-04.md) |
| ADR-05 | [Estrategia de procesamiento de video en Operix](adr/ADR-05.md) |

## Vigencia

La arquitectura v1.0 permanece cerrada. Esta incorporación publica artefactos existentes; no modifica el diseño ni certifica que el Backend/API, la aplicación web, PostgreSQL o el despliegue representado estén terminados. El Motor implementa actualmente solo las capacidades indicadas en el README principal.
