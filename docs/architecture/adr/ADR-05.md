# ADR-05 — Estrategia de procesamiento de video en Operix

Estado: Approved

Historial IcePanel: In progress (10/09/2026); Approved (10/09/2026).

---

Contexto

Operix debe analizar secuencias de video para identificar eventos de interés preventivo mediante detección de objetos, seguimiento multiobjeto, análisis espacio-temporal y reglas operacionales configurables.

Durante el levantamiento de requerimientos se identificó interés en visualizar el análisis sobre una fuente de video mientras esta se encuentra en ejecución. Sin embargo, el rendimiento del procesamiento depende de factores como el hardware disponible, resolución y tasa de cuadros de la fuente, modelo de detección utilizado y complejidad del pipeline.

Por esta razón, no resulta apropiado establecer inicialmente una garantía estricta de procesamiento en tiempo real sin contar con evidencia experimental del desempeño del prototipo.

Alternativas consideradas

1. Procesamiento exclusivamente diferido

Procesar archivos de video como trabajos que finalizan antes de entregar sus resultados.

Ventajas:





Implementación inicial sencilla.



No requiere mantener procesamiento continuo.



Facilita el análisis de material previamente registrado.

Desventajas:





No permite evaluar adecuadamente escenarios de monitoreo continuo.



Limita la posibilidad de visualizar resultados mientras ocurre el procesamiento.

2. Procesamiento exclusivamente en tiempo real

Diseñar el sistema bajo una exigencia estricta de procesamiento en tiempo real.

Ventajas:





Permite visualizar resultados durante la operación.



Favorece escenarios de monitoreo continuo.

Desventajas:





Impone requisitos de rendimiento antes de contar con mediciones experimentales.



Su factibilidad depende del hardware, fuente de video y configuración de los modelos.



Puede restringir innecesariamente el análisis de material previamente grabado.

3. Procesamiento continuo compatible con fuentes grabadas

Diseñar un pipeline común capaz de recibir frames provenientes tanto de fuentes continuas como de archivos de video, priorizando el procesamiento continuo y evaluando experimentalmente la latencia y tasa de procesamiento alcanzadas.

Ventajas:





Permite utilizar un mismo pipeline para fuentes continuas y grabadas.



Mantiene abierta la posibilidad de visualización cercana al tiempo real.



Permite determinar experimentalmente las capacidades y limitaciones del prototipo.



Evita imponer anticipadamente garantías de rendimiento no verificadas.

Desventajas:





Requiere gestionar diferentes tipos de fuentes de video.



La capacidad de operación cercana al tiempo real dependerá del escenario y hardware evaluado.

Decisión

Se adopta la alternativa 3.

Operix utilizará un pipeline común de análisis capaz de procesar frames provenientes de fuentes de video continuas o grabadas. El diseño priorizará el procesamiento continuo para permitir la evaluación de escenarios de monitoreo y visualización durante la ejecución.

No se establecerá inicialmente una garantía estricta de tiempo real. La capacidad de procesamiento en tiempo real o cercano al tiempo real será determinada experimentalmente mediante métricas de rendimiento, incluyendo tasa de procesamiento, latencia y características del entorno de ejecución.

El mecanismo específico para transportar y visualizar video y resultados dinámicos en la aplicación web será definido posteriormente de acuerdo con los resultados obtenidos durante la implementación y evaluación del prototipo.

Los mecanismos de colas de tareas para procesamiento diferido no formarán parte inicialmente del MVP y podrán incorporarse posteriormente si los escenarios de uso o resultados experimentales justifican su necesidad.

Justificación

Esta decisión permite responder al interés identificado durante el levantamiento de requerimientos respecto del análisis de video durante su ejecución, sin comprometer el proyecto con garantías de rendimiento que todavía no han sido verificadas.

Además, mantener un pipeline independiente del tipo de fuente permite reutilizar los componentes principales del motor de análisis —procesamiento de frames, detección, seguimiento, análisis espacio-temporal y evaluación de reglas— tanto sobre material grabado como sobre fuentes continuas.

La decisión también mantiene acotada la complejidad del MVP al evitar incorporar inicialmente infraestructura adicional para procesamiento diferido cuya necesidad todavía no ha sido demostrada.

Consecuencias

Positivas





Un mismo pipeline puede trabajar con fuentes continuas y grabadas.



Se mantiene la posibilidad de visualización cercana al tiempo real.



El rendimiento puede evaluarse objetivamente mediante FPS y latencia.



Se reduce la complejidad inicial del MVP.



La arquitectura permite incorporar posteriormente otros mecanismos de procesamiento si fueran necesarios.

Negativas





El rendimiento dependerá del hardware y de las características de la fuente de video.



Puede ser necesario optimizar el pipeline para alcanzar una latencia adecuada.



El mecanismo de transmisión y visualización de resultados en vivo queda pendiente de una decisión posterior.



El procesamiento diferido robusto mediante colas de tareas requeriría infraestructura adicional si posteriormente se considera necesario.
