# ADR-03 — Persistencia desacoplada del motor

Estado: Approved

Historial IcePanel: In progress (09/09/2026); Approved (10/09/2026).

---

Contexto

El Motor de análisis de video genera eventos y resultados a partir del procesamiento de secuencias de video. Estos datos deben almacenarse para permitir su consulta, trazabilidad y análisis histórico.

Se debe definir si el Motor accede directamente a la base de datos o si la persistencia es gestionada por la capa de aplicación.

Alternativas consideradas

1. Acceso directo del Motor a la base de datos

El Motor almacena directamente los eventos y resultados generados.

Ventaja: reduce los pasos necesarios para persistir los resultados.

Desventaja: acopla el procesamiento de video al mecanismo de persistencia y obliga al Motor a conocer la estructura y tecnología de almacenamiento.

2. Persistencia gestionada por Backend/API

El Motor entrega eventos y resultados al Backend/API, que se encarga de su persistencia.

Ventaja: mantiene separadas las responsabilidades de análisis y almacenamiento.

Desventaja: agrega una etapa de comunicación antes de persistir los resultados.

Decisión

La persistencia será gestionada por el Backend/API.

El Motor de análisis entregará los eventos y resultados generados al Backend/API y no accederá directamente a la base de datos.

Justificación

El Motor debe mantenerse enfocado en el procesamiento y análisis de video. Centralizar la persistencia en el Backend/API reduce el acoplamiento con la tecnología de almacenamiento y permite modificar la base de datos sin alterar directamente el pipeline de análisis.

Además, esta separación facilita centralizar la validación, trazabilidad y gestión de los datos generados por el sistema.

Consecuencias

Positivas





Reduce el acoplamiento entre análisis y persistencia.



Mantiene una responsabilidad clara para el Motor.



Centraliza el acceso a los datos en la capa de aplicación.



Facilita sustituir o modificar la tecnología de almacenamiento.



Favorece la trazabilidad de los eventos registrados.

Negativas





Los resultados deben transferirse al Backend/API antes de almacenarse.



Una falla de comunicación puede retrasar la persistencia de eventos.



Será necesario definir mecanismos para gestionar errores y reintentos.
