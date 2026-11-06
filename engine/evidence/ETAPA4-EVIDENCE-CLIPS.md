# Etapa 4 · Extractos anotados por evento

El Backend reserva mediante un enlace local el MP4 confirmado del run. Después de liberar la sesión de análisis, toma los eventos persistidos que coinciden en UUID de run, sesión, ordinal, SHA-256 de fuente y huella de configuración. Un proceso aparte extrae y codifica cada ventana sin volver a cargar modelos ni ejecutar reglas. La regla, versión, parámetros y geometría se consultan en el mismo evento que contiene el clip.

La ventana usa el fotograma del evento como ancla y la cadencia del MP4 para verificar sus tiempos. La configuración inicial usa cinco segundos por lado. La ventana se ajusta al inicio y al final de la fuente. El MP4 se identifica como **anotado**, se publica sin audio y mantiene los FPS del resultado. El PNG se conserva.

Los archivos se publican juntos por renombrado después de verificar el conteo decodificable, el FPS y el tamaño. El metadata incluye intervalo de fotogramas con extremo final exclusivo, tiempo del evento en la fuente, posición en el clip y huella del MP4. Los reintentos de la misma generación reutilizan un clip existente. El dossier añade el reproductor solo si la identidad del clip corresponde al evento y al run. La API comprueba la sesión de Django y el permiso de revisión antes de abrir el archivo, incluyendo solicitudes Range.

## Verificación

Backend 141/141, Motor 427 aprobadas y dos omitidas, Frontend 42/42, lint, typecheck, build y regresión Chromium con fixture aprobados.

- Pruebas de API para evento y run correctos, run ajeno, rechazo anónimo y rol sin permiso, caso histórico, idempotencia, límites de fuente, cuota, fallo del codificador y eliminación del evento.
- Control de contenido. Se extrajeron 12 fotogramas a partir de un desplazamiento no nulo. El fondo de intensidad variable coincidió con los fotogramas fuente 5–16, con una diferencia absoluta media máxima de 1,186 niveles por la recodificación.
- El recorrido real usa Demo C, CUDA, PostgreSQL aislado y proxy de Next. El evento de proximidad del fotograma 30 tiene una marca de 1,000 s. El extracto cubre los fotogramas 0–180 a 30 FPS, dura 6,033 s y sitúa el evento en el segundo 1,000 del clip.
- La corrida final confirmó el resultado a los 33,88 s, con 418/418 fotogramas, y generó dos extractos de 5.150.650 y 5.955.442 bytes. Chromium inició sesión y reprodujo el clip real en el dossier junto al PNG, con 640 px de ancho, 6,0333 s de duración, velocidad 1×, pausa y búsqueda al segundo del evento. El run incorrecto recibió 404. Ambos POST anónimos de E4-01 devolvieron 403.
- La extracción aislada de 211 fotogramas tomó aproximadamente 1,8 s, incluido el arranque de Python. La corrida completa no midió un coste aislado de ambos extractos ni una carga sostenida. En Windows se usa MSMF explícitamente tras observar fallos intermitentes con la selección automática del codificador.

## Límites

Un solo cupo de generación evita acumular trabajos y recursos. Un run que termina con el cupo ocupado conserva el evento y el PNG. No hay una cola durable ni regeneración automática de históricos. El MP4 fuente temporal se conserva mediante enlace mientras dura la extracción, en un sistema de archivos que admita enlaces físicos. El clip publicado usa un lado máximo de 640 px. Los 12 MiB por clip, 512 MiB acumulados y 24 eventos por run acotan el uso. Los clips quedan fuera de Git.

[Configuración y retención](../../backend/README.md#clips-anotados-de-evidencia).
