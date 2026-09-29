# ADR-04 — Selección del stack tecnológico de Operix

Estado: Approved

Historial IcePanel: In progress (09/09/2026); Approved (10/09/2026).

---

Contexto

Operix requiere una arquitectura tecnológica capaz de integrar una aplicación web, una API de negocio, persistencia relacional, procesamiento de video mediante visión artificial y un mecanismo reproducible de despliegue.

La selección tecnológica debe priorizar mantenibilidad, seguridad, madurez del ecosistema, facilidad de integración, experiencia previa del equipo y capacidad de evolución del prototipo, evitando incorporar complejidad operacional innecesaria durante el desarrollo del Trabajo de Título.

Además, la seguridad será tratada como una consideración transversal del desarrollo, considerando control de dependencias, gestión de vulnerabilidades, protección de secretos, mínimo privilegio y reducción de la superficie de exposición.

Alternativas consideradas

Frontend





Next.js + TypeScript



React con Vite



Vue / Nuxt



Angular

Backend / API





Django + Django REST Framework



FastAPI



NestJS

Persistencia





PostgreSQL



SQLite

Contenerización y orquestación





Docker + Docker Compose



Kubernetes



Ejecución directa sin contenedores

Decisión

Se utilizará el siguiente stack tecnológico base para Operix:





Frontend: Next.js + TypeScript.



Backend / API: Django + Django REST Framework.



Base de datos: PostgreSQL.



Motor de análisis de video: Python.



Procesamiento de video: OpenCV.



Detección de objetos: YOLO11 como selección inicial sujeta a validación experimental.



Seguimiento multiobjeto: ByteTrack como selección inicial sujeta a validación experimental.



Contenerización: Docker + Docker Compose.



Orquestación: Kubernetes no será incorporado al MVP.

Justificación

Next.js y TypeScript permiten desarrollar una interfaz web moderna, tipada y adecuada para configuración, consulta de eventos e indicadores, además de aprovechar experiencia previa con este ecosistema.

Django y Django REST Framework proporcionan una base madura para el manejo de usuarios, autenticación, permisos, validaciones, ORM, migraciones y exposición de servicios API, reduciendo la necesidad de implementar manualmente capacidades comunes de una aplicación empresarial.

PostgreSQL se selecciona como sistema de persistencia por su robustez, soporte transaccional, concurrencia, capacidades relacionales y posibilidad de representar configuraciones flexibles mediante tipos como JSONB. Durante el desarrollo puede ejecutarse localmente mediante contenedores sin requerir servicios administrados de pago.

Python se mantiene como lenguaje principal del motor de análisis por su integración natural con librerías de visión artificial y aprendizaje automático. OpenCV será utilizado para adquisición y procesamiento de video, mientras que YOLO11 y ByteTrack corresponden a selecciones iniciales para detección y seguimiento respectivamente.

Docker y Docker Compose permiten mantener entornos reproducibles y aislar los principales componentes del sistema sin introducir la complejidad operacional de una plataforma de orquestación distribuida.

Consideraciones de seguridad

El uso de componentes de código abierto no será considerado inseguro por sí mismo. Su utilización deberá acompañarse de buenas prácticas de desarrollo seguro, incluyendo:





uso de dependencias provenientes de fuentes confiables;



identificación y fijación de versiones;



revisión periódica de vulnerabilidades conocidas;



exclusión de secretos y credenciales del repositorio;



aplicación del principio de mínimo privilegio;



validación de entradas y configuraciones;



reducción de servicios expuestos públicamente;



aislamiento de la base de datos respecto de accesos externos innecesarios;



actualización controlada de imágenes y dependencias.

Consecuencias

Positivas





Uso de tecnologías maduras y ampliamente documentadas.



Reducción de fricción entre el motor de visión artificial y el ecosistema Python.



Disponibilidad de mecanismos de autenticación, permisos, ORM y migraciones mediante Django.



Persistencia robusta mediante PostgreSQL.



Reproducibilidad del entorno mediante Docker.



Menor complejidad operacional al excluir Kubernetes del MVP.



Incorporación explícita de prácticas de seguridad durante todo el ciclo de desarrollo.

Negativas





El stack utiliza múltiples tecnologías y requiere coordinación entre frontend, backend y motor de análisis.



Django introduce mayor estructura que frameworks minimalistas como FastAPI.



PostgreSQL requiere un servicio adicional respecto de alternativas embebidas como SQLite.



La separación entre Backend/API y motor de análisis requerirá definir un mecanismo de comunicación entre ambos.

Estado de las tecnologías experimentales

La arquitectura general y el stack base se consideran decisiones estables para el prototipo.

Sin embargo, YOLO11, ByteTrack, sus variantes concretas y el mecanismo de comunicación entre Backend/API y motor de análisis podrán modificarse si la evaluación experimental demuestra que otra alternativa satisface mejor los requisitos técnicos del sistema.
