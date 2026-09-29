# ADR-01 — Arquitectura híbrida y modular de Operix

Estado: Approved

Historial IcePanel: In progress (09/09/2026); Approved (10/09/2026).

---

Contexto

Operix debe transformar secuencias de video en eventos de interés preventivo mediante detección y seguimiento de objetos, análisis espacio-temporal y criterios operacionales configurables.

El sistema debe permitir además configurar dichos criterios, registrar los eventos generados y consultar posteriormente su evidencia e indicadores históricos. Estas responsabilidades presentan características distintas y pueden evolucionar de forma independiente.

Alternativas consideradas

1. Aplicación monolítica

Integrar la interfaz, procesamiento de video, reglas y persistencia dentro de una única aplicación.

Ventaja: menor complejidad inicial.

Desventaja: mayor acoplamiento entre el procesamiento de visión artificial, la lógica de aplicación y la persistencia, dificultando su evolución y evaluación independiente.

2. Arquitectura basada exclusivamente en modelos de IA

Delegar tanto la percepción como la interpretación de situaciones operacionales a modelos de inteligencia artificial.

Ventaja: posibilidad de modelar comportamientos complejos.

Desventaja: menor control y trazabilidad sobre criterios operacionales que deben ser configurables y validados según el escenario.

3. Arquitectura híbrida y modular

Separar las responsabilidades de interacción, coordinación, procesamiento de video y persistencia, combinando visión artificial con análisis espacio-temporal y reglas operacionales explícitas.

Decisión

Se adopta una arquitectura híbrida y modular para Operix.

La visión artificial será responsable de obtener información del entorno a partir del video, mientras que el análisis espacio-temporal y las reglas configurables permitirán evaluar dicha información según criterios operacionales definidos para cada escenario.

A nivel de contenedores, Operix se divide inicialmente en Aplicación Web, Backend/API, Motor de análisis de video y Base de datos.

Justificación

Esta alternativa permite separar responsabilidades, mantener trazabilidad sobre los criterios utilizados para generar eventos y modificar reglas o componentes tecnológicos sin rediseñar completamente el sistema.

La decisión también responde a los requerimientos levantados durante la Etapa 1, particularmente aquellos relacionados con procesamiento de video, seguimiento, zonas, reglas configurables, registro de eventos y consulta histórica.

Consecuencias

Positivas





Reduce el acoplamiento entre responsabilidades.



Facilita la modificación y evaluación independiente de componentes.



Permite mantener reglas operacionales explícitas y configurables.



Favorece la trazabilidad entre configuración, procesamiento y eventos.



Permite sustituir tecnologías concretas manteniendo la arquitectura general.

Negativas





Introduce mayor complejidad de integración que una aplicación monolítica.



Requiere definir interfaces claras entre los módulos.



Exige gestionar el intercambio de información entre el motor de análisis y la capa de aplicación.
