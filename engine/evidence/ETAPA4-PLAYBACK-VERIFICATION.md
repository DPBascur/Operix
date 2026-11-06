# Etapa 4 · Vista previa y reproducción final

El flujo web prelee y decodifica la fuente para comprobar su cadencia. El Motor procesa y anota todos los fotogramas y valida que el H.264 final conserve cantidad, resolución y FPS. Los FPS de procesamiento incluyen trabajo del pipeline. La duración del MP4 se obtiene de sus fotogramas y su cadencia, y es independiente del tiempo que tome el análisis.

Durante el análisis, el navegador recibe JPEG muestreados por HTTP, con un objetivo de 10 muestras/s en el perfil web. No hay un reproductor MP4 en esa etapa. El preview depende del último fotograma disponible y puede detenerse o saltar cuando el pipeline o la entrega se retrasan. La prueba negativa creó un resultado confirmado al inicio del reloj de preview. Antes del cambio, el servidor seguía informando preview pendiente y el frontend retrasaba el reproductor hasta alcanzar el final visual. Después, el preview termina al confirmarse el resultado y el MP4 se ofrece de inmediato. La UI identifica el muestreo y separa los FPS de procesamiento de los FPS del resultado.

## Controles de duración

Dos clips CFR MJPEG de 200×100 con fotogramas sintéticos, worker real con detecciones fixture y codificación H.264. Se decodificaron las fuentes y las salidas completas.

| FPS fuente → MP4 | Fotogramas | Duración fuente → MP4 | Último timestamp fuente → MP4 | FPS de procesamiento fixture |
| --- | ---: | ---: | ---: | ---: |
| 12,5 → 12,5 | 30 → 30 | 2,400 → 2,400 s | 2,320 → 2,320 s | 152,86 |
| 30 → 30 | 60 → 60 | 2,000 → 2,000 s | 1,967 → 1,967 s | 174,18 |

Las detecciones fixture permiten probar el reloj y el códec. Sus FPS de procesamiento no estiman el rendimiento de YOLO. El preflight conserva la política previa para VFR y las advertencias cuando el decodificador no ofrece timestamps verificables.

## Demo C y navegador

La auditoría anterior registró 418 fotogramas a 30 FPS y 13,933 s de contenedor, con 15,63 FPS de procesamiento y 31,92 s desde START en la corrida con callback `localhost`. La nueva corrida con CUDA y PostgreSQL aislado conservó **418 fotogramas, 30 FPS y 13,933 s**. Produjo H.264 con MSMF, procesó a 13,73 FPS y confirmó el resultado en 35,94 s desde START. Se midieron 4,43 ms de decodificación, 21,293 ms de detector PERSON, 12,899 ms de detector FORKLIFT, 11,051 ms de render y 1,951 ms de escritura por fotograma. Son mediciones descriptivas de corridas distintas. El cambio elimina la espera impuesta por el reloj del preview después de confirmar el resultado.

En Chromium, la prueba autenticada con API fixture presentó el preview muestreado y abrió el MP4 aunque la fixture todavía anunciaba preview pendiente. Comprobó reproducción a 1×, duración cercana a 277/30 s, pausa y búsqueda. La corrida CUDA comprobó Range 206 y rechazo 404 del run ajeno. Se conservó la entrega puntual del último JPEG para el contrato previo de preview sin muestreo.

## Reproducción

- La regresión `PreviewStreamTests.test_completed_result_does_not_wait_for_preview_clock` verifica el paso inmediato a resultado con el reloj detenido. Las pruebas del reloj mantienen cobertura de fuente lenta, tasa fraccional y muestreo.
- Para repetir los controles, generar AVI MJPEG con OpenCV a 12,5 FPS y 30 FPS, de 30 y 60 fotogramas respectivamente. Ejecutar `backend/apps/analysis/fixtures/perception_worker.py` con el script `engine/scripts/stream_dual_perception.py`, un perfil válido, batch 1 y archivos existentes como placeholders de pesos fixture. Contrastar `CAP_PROP_FPS`, el conteo decodificado y `CAP_PROP_POS_MSEC` de fuente y `annotated.mp4`.
