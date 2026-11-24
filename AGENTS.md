# Operix

## Desarrollo y despliegue local

- La instancia habitual de revisión es Operix en `http://127.0.0.1:13000`. Entrega cada mejora verificada allí. Usa QA para experimentos y validaciones aisladas.
- Para cambios de Frontend, ejecuta las regresiones, actualiza solo ese servicio en 13000 y comprueba el flujo afectado en Edge.
- Para cambios de Backend, Motor, seguridad o persistencia, valida primero en QA. Verifica migraciones, compatibilidad y estado de cámaras. Si el cambio puede afectar datos, verifica un respaldo antes de actualizar y conserva una ruta de recuperación.
- Actualiza únicamente los servicios necesarios. Conserva PostgreSQL, MediaMTX, configuraciones, evidencias y volúmenes. Comprueba la salud, el flujo afectado y la integridad posterior. Si falla una comprobación crítica, recupera la versión anterior y registra el bloqueo.
- Ejecuta comparaciones de GPU en QA por separado. Comprueba que las cámaras del entorno habitual estén inactivas y conserva el registro de interferencia. Mantén los pesos congelados y las fuentes autorizadas fuera de los cambios.
- Trabaja en `dev`, preserva archivos locales ajenos y deja `main`, tags y el Product Backlog intactos. Publica únicamente con autorización expresa.

Consulta [el recorrido del laboratorio](deployment/rtsp-lab/README.md) para las pruebas de cámara, calibración y demostración.
