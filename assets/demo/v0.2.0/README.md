# Demo actual — candidato v0.2.0

Una ejecución real del MVP sobre la demo sintética C (box pickup). No es una
maqueta ni evaluación final: una condición configurada satisfecha requiere
revisión humana y no confirma incidente, Near Miss, accidente o culpabilidad.

## Material

- [Captura actual del análisis](analysis-result.png), recapturada después de
  unificar la geometría de botones entre light y dark.
- [Configuración exacta](config.json) y [recibo de identidad/metadatos](metadata.json).

La única captura versionada es del build de producción a 1440×1000, con API real
y PostgreSQL de pruebas aislado. Los registros/PNG proceden del Motor; no se usa
la API fixture del test browser. La fecha civil es ancla del análisis, no fecha
real de grabación.

El video de QA/demostración y las capturas auxiliares permanecen fuera de Git.
El video completo es una salida temporal de sesión; los eventos guardan su
PNG/snapshot, no ese MP4 completo. metadata.json conserva las identidades de
los videos externos para trazabilidad, sin enlaces ni rutas locales.

## Input y configuración

Fuente autorizada de desarrollo: NVIDIA PhysicalAI WorldModel Synthetic Warehouse
Operations Scenes, `warehouse_box_pickup`, run
`008caa590c5e5b7b4bca_run_8_seed_4731920`, cámara `cam_00`.
Archivo original `008caa590c5e5b7b4bca_run_8_seed_4731920.cam_00.rgb.mp4`, SHA-256
`eabf44d7abe50d1bf4824f238a9f0ac9ddc29419e10d66b89c6a92cb1b98329c`.
El input permanece fuera de Git; no es un holdout ni una escena de empresa.
[Procedencia y licencia OpenMDW-1.1](../../../third_party/nvidia-warehouse-dataset/NOTICE.md).

PERSON usa YOLO11M_COCO_PERSON, 640 / 0,10 / NMS 0,70, batch 1, FP32, CUDA:0;
FORKLIFT specialist v2 conserva 640 / 0,45 / NMS 0,55. Los dos SHA completos están
en metadata.json y en la [guía Backend](../../../backend/README.md#person-operacional-posterior-a-evaluación).
ByteTrack y geometría `person_equipment_nearest_ground_edges_v1` no cambian.

config.json es una copia byte a byte de la configuración de regresión controlada
ya utilizada antes de esta campaña: zona C de ocho vértices, zone_dwell de 2 s y
TEST_DATA_PAIR con máximo 0,25 normalizado / mínimo 1 s. No se modificó ningún
umbral para producir el resultado. **No es el perfil C predeterminado**: se usa
expresamente esta configuración de demostración, sin cambiar perfiles productivos.

## Recorrido Web reproducible

1. Preparar Motor, Backend y Frontend según sus README. Usar una base PostgreSQL
   exclusiva de demo y media separados; no reutilizar registros operativos.
2. Proporcionar ambos checkpoints externos verificados y el input autorizado
   obtenido del dataset. Configurar OPERIX_DEMO_VIDEO_C a ese archivo local,
   OPERIX_PERSON_WEIGHTS a yolo11m.pt y OPERIX_FORKLIFT_WEIGHTS al specialist v2.
   Cargar el entorno del Backend antes de ejecutar migraciones/iniciar la API.
3. Desde backend, iniciar el servidor con el fixture explícito de esta demo:

   ```powershell
   .\.venv\Scripts\python.exe manage.py shell -c "from django.core.management import call_command; from apps.analysis import sessions; sessions.PROFILES['C'] = sessions.ROOT / 'assets/demo/v0.2.0/config.json'; call_command('runserver', '127.0.0.1:8000', use_reloader=False)"
   ```

   La sustitución solo vive en ese proceso demostrativo; no edita código ni el
   perfil por defecto. Configurar EVENT_POST_ENABLED=1 únicamente en esta API local
   controlada para guardar los candidatos y usar CORS/URL de Frontend coherentes.
4. En la Web, seleccionar Demo C, iniciar, esperar análisis y guardado, revisar el
   resultado, abrir Eventos y el detalle de proximidad. Los umbrales son de fixture,
   no una recomendación operacional universal. No ajustar parámetros para igualar
   conteos; documentar diferencias si cambia hardware/runtime.

Si falla el Motor, revisar el error o mostrar registros previos con su fecha y
origen explícitos; no presentarlos como una ejecución nueva ni sustituirlos por
el dashboard ilustrativo. Ante un fallo de publicación, conservar el journal y
seguir la recuperación descrita en la guía Backend.

Los checkpoints no se distribuyen aquí. Una configuración sin la regla de pares
habilitada no debe prometer el mismo evento de proximidad.

## Regenerar solo el resultado de video

Desde la raíz, verificar primero input y checkpoints contra metadata.json. Crear
un directorio de salida nuevo fuera del repositorio y usar el worker existente:

```powershell
.\engine\.venv\Scripts\python.exe engine/scripts/stream_dual_perception.py `
  --session-dir '<directorio nuevo de salida>' --video '<input verificado>' `
  --config assets/demo/v0.2.0/config.json --batch-size 1 `
  --person-weights '<pesos externos yolo11m.pt>' `
  --person-sha256 d5ffc1a674953a08e11a8d21e022781b1b23a19b730afc309290bd9fb5305b95 `
  --forklift-weights '<pesos externos specialist v2>' `
  --forklift-sha256 1465105ea80737ddc65d72e97d6dc24fc253995a98d6d4eea9b377fe3a8edce6
```

Sin event-context esta CLI no publica por HTTP. Para eventos/evidencia/histórico,
usar el recorrido Web anterior. Nueva codificación no implica identidad binaria
con el video externo de QA. No sobrescribir históricos OP-60/61.

## Lectura del resultado y límites

Se procesaron 418/418 frames, con dos eventos guardados: proximidad en frame 30 y
permanencia en frame 60. Son resultados de esta ejecución, no un criterio de éxito
universal ni métricas de exactitud. La línea representa los puntos más próximos
de ambos segmentos inferiores; la distancia es de imagen normalizada, no metros.
Pérdidas de tracking pueden reiniciar episodios. No hay supresión de ocupantes,
identificación personal, soporte TRUCK ni validación industrial.

La UI y los overlays son de Operix; los píxeles sintéticos subyacentes, también
visibles en las capturas, conservan la atribución/licencia NVIDIA del NOTICE.
Los [clips históricos](../README.md) se mantienen como antecedentes independientes.
