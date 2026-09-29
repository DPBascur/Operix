# Arquitectura de Operix v1.0

La línea base **Operix Architecture v1.0** se cerró el 10/09/2026. Los diagramas siguientes documentan el **diseño arquitectónico**; su presencia aquí no significa que todos los componentes o flujos representados estén implementados. Para distinguir el estado del software, consultar el [README principal](../../README.md).

## Diagramas

Los tres C4 se extrajeron sin redibujar de la [exportación completa de IcePanel](architecture-v1.0-icepanel-export.pdf), que conserva además el índice y las descripciones de actores, sistemas y componentes.

| ID | Artefacto | Archivo | Página del PDF original |
| --- | --- | --- | --- |
| C4-01 | Contexto | [C4-01-contexto.pdf](C4-01-contexto.pdf) | 2 |
| C4-02 | Contenedores | [C4-02-contenedores.pdf](C4-02-contenedores.pdf) | 3 |
| C4-03 | Componentes del motor | [C4-03-componentes-motor.pdf](C4-03-componentes-motor.pdf) | 4 |
| SEQ-01 | Flujo de procesamiento de un evento preventivo | [SEQ-01-flujo-evento.png](SEQ-01-flujo-evento.png) | No aplica |
| ERD-01 | Modelo de datos | [ERD-01-modelo-datos.png](ERD-01-modelo-datos.png) | No aplica |
| DEP-01 | Diagrama de despliegue | [DEP-01-despliegue.png](DEP-01-despliegue.png) | No aplica |

## Decisiones de arquitectura

ADR-01 a ADR-05 pertenecen a la arquitectura base v1.0. Sus exportaciones originales desde IcePanel están **pendientes de incorporación al repositorio**. Este índice no reconstruye sus títulos ni sus decisiones.

## Vigencia

La arquitectura v1.0 permanece cerrada. Esta incorporación publica artefactos existentes; no modifica el diseño ni certifica que el Backend/API, la aplicación web, PostgreSQL o el despliegue representado estén terminados. El Motor implementa actualmente solo las capacidades indicadas en el README principal.
