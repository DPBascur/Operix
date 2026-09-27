# Índice de arquitectura

La línea base vigente es **Operix Architecture v1.0**, cerrada el 10/09/2026. Este índice localiza los artefactos aceptados sin reemplazar ni reproducir la documentación académica.

Este README es el único índice de arquitectura versionado aquí. Enumera once
artefactos de la línea base: seis diagramas (C4-01/02/03, SEQ-01, ERD-01 y
DEP-01) y cinco decisiones (ADR-01 a ADR-05). El contenido completo de esos
once artefactos permanece externo y no se obtiene al clonar el repositorio.
Las referencias usan identificador, nombre de archivo o página para localizar
la copia académica autorizada; no son enlaces a archivos incluidos en Git.

## Diagramas

Los siguientes artefactos se conservan externamente en la colección académica de diagramas. No están versionados ni forman parte de un clon del repositorio. Se indican sus nombres, sin enlaces dependientes de la organización local ni rutas privadas.

| ID | Artefacto | Referencia externa (no versionada) |
| --- | --- | --- |
| C4-01 | Context Diagram | `DPBascur_s landscape (Current).pdf`, página 2 |
| C4-02 | Container Diagram | `DPBascur_s landscape (Current).pdf`, página 3 |
| C4-03 | Component Diagram del Motor | `DPBascur_s landscape (Current).pdf`, página 4 |
| SEQ-01 | Flujo de procesamiento de un evento preventivo | `SEQ-01 - Flujo de procesamiento de un evento.png` |
| ERD-01 | Modelo de datos | `ERD-01 — Modelo de datos de Operix.png` |
| DEP-01 | Diagrama de despliegue | `DEP-01 — Diagrama de despliegue de Operix.png` |

## Decisiones de arquitectura

**ADR-01 a ADR-05: Aceptados en IcePanel; contenido completo aún no versionado en el repositorio.**

Se conservan sus identificadores y estado de aceptación. Este índice no recrea su contenido por inferencia.

## Vigencia

La implementación debe respetar esta línea base. Si aparece una limitación técnica que requiera modificar arquitectura o stack, se documentarán el problema, la evidencia y la propuesta para evaluar una nueva decisión arquitectónica antes de aplicar el cambio.
