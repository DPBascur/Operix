# ADR-02 — Separación del motor de análisis y Backend

Estado: Approved

Historial IcePanel: In progress (09/09/2026); Approved (10/09/2026).

---

Contexto

El procesamiento de video de Operix requiere ejecutar tareas de visión artificial, seguimiento y análisis espacio-temporal que pueden tener una carga computacional y un ciclo de ejecución distintos a las operaciones de configuración, consulta y persistencia.

Integrar ambas responsabilidades en una misma unidad aumentaría el acoplamiento entre el procesamiento inteligente y la lógica de aplicación.

Alternativas consideradas

1. Integrar el motor dentro del Backend/API

El Backend ejecuta directamente el procesamiento de video junto con las operaciones de configuración, consulta y persistencia.

Ventaja: menor complejidad inicial de integración.

Desventaja: acopla tareas computacionalmente intensivas con las responsabilidades de la API y dificulta su evolución independiente.

2. Separar Motor de análisis y Backend/API

El Motor se encarga del procesamiento de video y entrega sus resultados al Backend/API, mientras este coordina configuración, consultas y persistencia.

Ventaja: separación clara de responsabilidades y posibilidad de evolucionar ambos contenedores de forma independiente.

Desventaja: requiere definir un mecanismo de comunicación entre ambos.

Decisión

Se separa el Motor de análisis de video del Backend/API.

El Backend/API proporcionará la configuración necesaria y coordinará el procesamiento, mientras que el Motor analizará las secuencias de video y devolverá los eventos y resultados obtenidos.

Justificación

El procesamiento de video posee características diferentes a las operaciones habituales de una API. Separarlo permite aislar la carga asociada a visión artificial y mantener el Backend/API enfocado en la coordinación de la aplicación, las consultas y la persistencia.

Esta separación también permite evaluar y modificar el pipeline de análisis sin afectar directamente la interfaz o la capa de persistencia.

Consecuencias

Positivas





Separa el procesamiento intensivo de la lógica de aplicación.



Reduce el acoplamiento entre visión artificial y Backend/API.



Facilita evaluar y sustituir componentes del pipeline de análisis.



Permite evolucionar el motor y la aplicación de manera independiente.

Negativas





Requiere definir una interfaz de comunicación entre Backend/API y Motor.



Introduce mayor complejidad de integración.



Será necesario gestionar errores y estados del procesamiento entre ambos contenedores.
