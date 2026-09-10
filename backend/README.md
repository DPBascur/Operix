# Backend/API

Componente de Operix Architecture v1.0 encargado de gestionar configuración, consultas y comunicación entre la aplicación web, el motor de análisis y la persistencia.

- Stack aprobado: Django + Django REST Framework.
- Gestiona el acceso y la persistencia en PostgreSQL.
- Proporciona configuración y controla el procesamiento del motor; recibe sus eventos, resultados y estado de análisis.
- Estado: implementación pendiente. Esta carpeta documenta la responsabilidad del componente.

El motor entrega sus resultados a esta API y no accede directamente a PostgreSQL. Consulte el [índice de arquitectura](../docs/architecture/README.md) para los artefactos vigentes.
