# Etapa 4 · Piloto RTSP de una fuente

## Capacidad de referencia

Las trazas originales separan la cadencia del video, la tasa de salida tras calentamiento y el throughput de pared. En la primera corrida de 1080p, 418 cuadros en 26,653 s equivalen a **15,68 FPS de pared**. El valor de **26,85 FPS** usa únicamente los intervalos de salida después de los primeros 20 cuadros. El propio worker informó 19,89 FPS para otra ventana que empieza después de la preparación. Para 540p/12, 720 cuadros en 33,179 s equivalen a **21,70 FPS de pared** frente a 29,68 FPS sostenidos. Las llamadas sincronizadas a los detectores en esa corrida tomaron 16,990 y 12,493 ms medios por cuadro. Estas medidas incluyen su pre y postprocesamiento y no permiten inferir una tasa de kernels GPU ni una latencia hasta el navegador.

## Uso y alcance

El piloto se ejecuta en un proceso independiente del Backend. Reutiliza los detectores y pesos fijados, ByteTrack por clase, el analizador geométrico y RuleEngine. La salida es un diario local de candidatos y telemetría, con UUID de sesión, época, configuración exacta y huellas. La separación evita publicar pruebas como eventos del entorno principal. Las rutas web, los roles y el token interno mantienen su frontera existente.

La ejecución requiere `OPERIX_RTSP_PILOT=1`. Configure `OPERIX_RTSP_URL` en el entorno privado del proceso. Por defecto se acepta el destino literal 127.0.0.1. Para un piloto autorizado en otra red se requiere `OPERIX_RTSP_ALLOWED_IP` con la IP literal exacta y una política de egreso que limite el destino, incluidas redirecciones del cliente RTSP. No pasar la URL por argumentos ni copiarla en el diario. El piloto consume una sola URL por ejecución. La admisión GPU de Django sigue siendo independiente, por lo que se debe reservar la GPU y evitar ejecutar el piloto junto al worker web.

```powershell
# Ejecutar en la raíz de Operix con los pesos locales en variables de entorno.
$env:OPERIX_RTSP_PILOT = '1'
$env:OPERIX_RTSP_URL = 'rtsp://127.0.0.1:18554/fixture'
& engine/.venv/Scripts/python.exe -B engine/scripts/run_rtsp_pilot.py `
  --config $configLocal --output $carpetaNueva `
  --person-weights $env:OPERIX_PERSON_WEIGHTS `
  --forklift-weights $env:OPERIX_FORKLIFT_WEIGHTS --seconds 55
```

Detener con Ctrl+C o con el límite de duración. Desactivar quitando `OPERIX_RTSP_PILOT`. Usar una carpeta nueva por corrida, fuera de Git. `summary.json` conserva los contadores y percentiles, `frames.ndjson` la traza y `candidates.ndjson` los candidatos. No contiene evidencia visual. El operador del sistema controla permisos y retención de estos archivos.

El lector usa RTSP/RTP sobre TCP intercalado, con timeout de apertura de 2,5 s y de lectura de 1,5 s. Los fallos consecutivos aplican espera creciente entre 0,25 y 5 s. La cola tiene seis cuadros, descarta el más antiguo al saturarse y expira cuadros pendientes de más de 500 ms. Se descartan y contabilizan cuadros que quedan pendientes al cortar o detener. El piloto asigna un índice consecutivo a cada cuadro decodificado y conserva el PTS que entrega OpenCV cuando está disponible. La edad empieza cuando el decodificador entrega el cuadro y usa un reloj monotónico. La medición termina tras evaluar reglas, antes de escribir el diario. Quedan fuera las pérdidas y el buffering anteriores a la entrega del decodificador, la persistencia web y el navegador. Un hueco de PTS, salto de índice, corte, cambio de reloj o reconexión inicia una nueva época y reinicia ambos trackers, analizador y reglas. Los track IDs solo son comparables dentro de una época.

## Emisor reproducible

`engine/tests/fixtures/rtsp_emitter.py` abre un MP4 H.264 local en modo Annex B y transmite unidades de acceso a su cadencia original en loopback. No requiere un servidor instalado. La prueba usó los 720 cuadros de `sustained-540p12.avi` del estudio, recodificados a H.264 mediante OpenCV/MSMF, sin anotaciones, a 960×540 y 12 FPS. El SHA-256 de esa recodificación fue `2b0de6a7c8a36a8b22d3323c7364562f30e63c89c024c6453c59a366878ffe7e`. Para repetir el escenario de eventos se utiliza el snapshot de la corrida offline de dos detectores, con la regla de prueba `TEST_DATA_PAIR` (máximo normalizado 0,25 y duración mínima de 1 s) además de la regla de permanencia del demo. El snapshot exacto quedó en los artefactos locales de las corridas. Los parámetros de producción se conservaron.

```powershell
# En otra consola, antes de iniciar el piloto.
& engine/.venv/Scripts/python.exe -B engine/tests/fixtures/rtsp_emitter.py $videoH264
# Para la corrida con fallos, arrancar un emisor nuevo.
& engine/.venv/Scripts/python.exe -B engine/tests/fixtures/rtsp_emitter.py $videoH264 `
  --port 18555 --cut-first 100 --damage-first-at 65
```

Para el segundo caso usar el puerto 18555 en `OPERIX_RTSP_URL` y `--seconds 28`. Para repetir la carga extendida, usar el puerto 18554 y `--seconds 175`. El emisor vuelve al cuadro inicial en cada conexión, también tras el final natural del clip de 60 s. Detenerlo por separado al terminar.

Para reconstruir el snapshot de prueba en una carpeta local, usar como base `engine/config/examples/warehouse-box-pickup-zone-dwell.json` y agregar al final de `rules`:

```json
{
  "rule_id": "TEST_DATA_PAIR",
  "version": 1,
  "enabled": true,
  "parameters": {
    "kind": "person_forklift_proximity",
    "zone_id": "pasillo_cajas_demo",
    "person_class": "person",
    "forklift_class": "forklift",
    "max_distance": 0.25,
    "minimum_duration_seconds": 1.0
  }
}
```

Serializar con `json.dumps(config).encode("utf-8")`, sin salto final. El SHA-256 de referencia es `f3da54c372902ff9ae3868d005c0fbab6f10852fb7a6b8e8129cc4404aaa51d5`. El diario registra la huella del archivo efectivamente usado en cada corrida.

## Resultados de loopback

RTX 3070 y Ryzen 5 5500, PERSON y FORKLIFT en CUDA, una fuente a 540p/12 FPS. Los FPS efectivos dividen los cuadros procesados por el tiempo de pared de la sesión, incluidas apertura, reconexiones y detención. El calentamiento previo se registra aparte. El p95 selecciona el valor en la posición `ceil(0.95 × n)` de las muestras ordenadas. En sesiones más largas el resumen conserva las últimas 8.192 muestras y el diario conserva todas. La profundidad por cuadro indica el tamaño de la cola inmediatamente después de encolarlo.

| Corrida | Pared | Procesados / decodificados | FPS efectivos | Descartes de cola / corte / cierre | Profundidad máx. | p95 edad / llegada→resultado / servicio |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Sin corte | 55,089 s | 640 / 661 | 11,62 | 20 / 0 / 1 | 6 | 0,06 / 45,74 / 44,60 ms |
| Corrupción y corte | 28,117 s | 289 / 334 | 10,28 | 43 / 1 / 1 | 6 | 59,07 / 91,61 / 43,59 ms |
| Extendida, dos finales de clip | 175,124 s | 2.029 / 2.095 | 11,59 | 65 / 0 / 1 | 6 | 0,06 / 45,67 / 44,97 ms |

Los 20 descartes de cola de la corrida sin corte se concentraron en la ráfaga inicial, antes de llegar al índice 23. La prueba con fallos registró un hueco de PTS, un fallo de lectura y dos conexiones. Transcurrieron 2,603 s entre el último cuadro procesado de la primera conexión y el primero de la segunda, medidos por sus marcas locales de llegada. El adaptador contabiliza fallos de lectura sin distinguir un corte de un error interno del decodificador. El recuento de cuadros decodificados cuadró con los procesados y los descartes en ambas corridas. Los 10 y 9 candidatos conservaron la huella del snapshot y ningún episodio atravesó un límite de época. Un Ctrl+C simulado durante una tercera sesión procesó 61 cuadros y dejó el resumen con terminación `operator_stop`. Un destino fuera de la lista permitida se rechazó sin mostrar la credencial ficticia ni crear una carpeta de salida. Las pruebas automatizadas cubren saturación, fallos de apertura/lectura, reinicio de época y cierre del lector. La suite del Motor obtuvo 432 aprobadas y 2 omitidas.

## Gate de cámara

En la corrida extendida, 1.998 de los 2.029 cuadros procesados entraron con profundidad uno. Los saltos de cola aparecieron durante la apertura inicial o tras reconectar por el final del clip. Los 30 candidatos de esta corrida también conservaron el snapshot y permanecieron dentro de su época.

Falta una cámara autorizada. El gate requiere tres corridas de 30 min a 540p/12 FPS, cero descartes bajo red estable, cola sin crecimiento sostenido, p95 local llegada→resultado inferior a 500 ms, una reconexión comprobada y evidencia de que ningún episodio cruza el corte. Los descartes de apertura observados son el primer punto a investigar. Separar los cuadros recibidos en ráfaga de una cámara de los que acumula el decodificador antes de entregar su primer cuadro.

Para la prueba real, usar una red controlada con egreso limitado a la cámara, asociar su identificador no sensible al UUID de corrida en el registro del operador y reservar la GPU para el ensayo. RTSP sobre TCP por sí solo carece de cifrado de transporte. La edad desde el instante de captura requiere un reloj externo verificado. Evaluar además pérdidas anteriores al decodificador, retención y acceso al diario local antes de exponer el piloto a más operadores. La persistencia de eventos y clips por el canal autorizado queda para una fase posterior.
