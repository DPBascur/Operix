# Etapa 4 · Acceso y autorización

El login demostrativo conservaba una identidad local al navegador y las rutas de lectura del Backend eran públicas. La publicación E4-01 ya exigía un token interno.

## Decisión de acceso

Se aplicó la política mínima descrita en el plan de cierre de Etapa 4 para OP-77. El usuario gestiona sus propios análisis, el responsable de seguridad revisa eventos y el administrador gestiona cuentas y tiene acceso operativo. La arquitectura v1.0 establece el principio de mínimo privilegio. La asignación de responsables a sitios o conjuntos de eventos queda pendiente de validación con OP-46. Los eventos históricos carecen de esa asignación.

- Django autentica con contraseñas hasheadas y sesiones en PostgreSQL. El inicio de sesión rota la identidad de sesión, el cierre la invalida en el servidor y el vencimiento se fija en ocho horas.
- Las cookies de sesión y CSRF son HttpOnly y SameSite=Lax. Las operaciones de escritura del navegador requieren un token CSRF obtenido del servidor. En HTTPS se activan también las cookies Secure.
- El Backend comprueba el rol en consultas y mutaciones, además de la propiedad de cada sesión temporal al acceder a fuente, preview, resultado, estado y reintento. Los identificadores ajenos reciben 404. Django Admin conserva la gestión de cuentas y grupos.
- El token interno E4-01 solo autoriza la publicación de eventos y PNG. El proxy usa el mismo origen y Django valida la autorización independientemente de la ruta de entrada.

## Verificación

- Backend y PostgreSQL. 137 pruebas aprobadas, incluidas credenciales inválidas, CSRF ausente y origen no autorizado, expiración real de la fila de sesión, recuperación, revocación de rol, permisos por ruta, aislamiento de análisis y publicación interna.
- Motor. 427 aprobadas y dos omitidas. Frontend. 41 aprobadas, lint, typecheck y compilación aprobados.
- Chromium con API fixture. El acceso directo redirigió al login, se mostró el error de credenciales, se recuperó la ruta tras una expiración simulada y el cierre de sesión volvió a bloquear la navegación. Pasaron el flujo de análisis, las comprobaciones de evidencia y 18 combinaciones de ancho y ruta.
- Corrida real aislada de Demo C con CUDA y PostgreSQL. 418 frames y dos eventos persistidos. Mediante el proxy, el historial anónimo devolvió 401, el login por cookie devolvió 200 y el historial y el PNG fueron accesibles. Tras cerrar sesión, el historial volvió a devolver 401.
- E4-01 por el proxy. Los POST anónimos de evento y PNG devolvieron 403 sin escrituras. El recorrido legítimo del Motor mantuvo la publicación y evidencia.

## Límites

La autorización de un MP4, PNG o stream se comprueba al abrir cada solicitud. Una conexión ya abierta no se revoca retroactivamente. La interfaz abandona las vistas protegidas cuando la sesión se pierde. Quedan por definir el límite de intentos de login, la separación por sitio y la operación con múltiples procesos. Docker Compose se comprobó en configuración. La corrida real se ejecutó en el entorno nativo.

[Configuración de cuentas, HTTPS y token interno](../../backend/README.md#acceso-y-despliegue).
