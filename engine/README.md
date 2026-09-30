# Motor de análisis de video

Componente de Operix Architecture v1.0 que transforma video en resultados de análisis. La regla inicial emite candidatos transitorios; la gestión persistente de eventos aún no está implementada.

> La IA percibe el entorno; las reglas interpretan el contexto.

Flujo conceptual actual: video → detección → tracking → variables espacio-temporales → reglas configurables → `EventCandidate` en memoria. Backend/API y registro/histórico son pasos futuros de la arquitectura.

## Tecnologías y límites

- Python 3.12 x64 y OpenCV para procesamiento de video.
- YOLO11 para detección y ByteTrack para seguimiento, como selecciones iniciales y experimentales.
- La arquitectura prevé recibir configuración del Backend/API y entregarle resultados; esa integración aún no está implementada.
- Sin acceso directo a PostgreSQL.
- Reglas y umbrales configurables según escenario y organización, sin valores operacionales universales fijados en código.

## Entorno local

El entorno del motor se crea en `engine/.venv`. PyTorch y TorchVision deben instalarse antes que el proyecto, usando la distribución oficial correspondiente a la plataforma. Después, la instalación editable de `engine` agrega las dependencias comunes declaradas en `pyproject.toml`.

Desde la raíz del repositorio, en PowerShell:

```powershell
py -3.12 -m venv .\engine\.venv
.\engine\.venv\Scripts\python.exe -m pip install --upgrade pip
```

Si el lanzador `py` no registra Python 3.12, puede crearse el entorno con la ruta de instalación por usuario:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .\engine\.venv
```

### Windows con GPU NVIDIA

La configuración validada para el equipo principal usa PyTorch 2.14.0, TorchVision 0.29.0 y las ruedas oficiales CUDA 13.0 (`cu130`). Estas ruedas incluyen las bibliotecas de ejecución requeridas; no se instala CUDA Toolkit ni `nvcc`.

```powershell
.\engine\.venv\Scripts\python.exe -m pip install torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cu130
```

### CPU

```powershell
.\engine\.venv\Scripts\python.exe -m pip install torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cpu
```

### macOS con Apple Silicon

La instalación compatible con MPS se validará posteriormente en un equipo Apple Silicon. No se considera validada como parte de OP-59.

### Dependencias comunes y verificación

```powershell
.\engine\.venv\Scripts\python.exe -m pip install --editable .\engine
.\engine\.venv\Scripts\python.exe -m pip check
.\engine\.venv\Scripts\python.exe .\engine\scripts\check_environment.py
```

El comando anterior verifica el entorno también en CPU. En el equipo Windows/NVIDIA
validado, exigir CUDA explícitamente:

```powershell
.\engine\.venv\Scripts\python.exe .\engine\scripts\check_environment.py --require-cuda
```

El mecanismo de selección de dispositivo sigue el orden `CUDA → MPS → CPU`. En el entorno Windows/NVIDIA validado se comprobaron operaciones reales de tensores tanto CUDA como CPU. La instalación CPU no implica que los scripts de demostración configurados con `--device cuda` puedan ejecutarse sin cambiar ese argumento.

El verificador dirige la configuración que Ultralytics crea al importarse hacia `.venv`, evitando generar archivos locales sin seguimiento en la raíz del repositorio. No descarga pesos ni procesa videos.

### Entorno congelado validado

`pyproject.toml` mantiene las dependencias comunes del proyecto. PyTorch y TorchVision se instalan primero con la distribución correspondiente a cada plataforma.

`requirements.windows-cu130.lock.txt` registra exclusivamente las versiones exactas del entorno probado en Windows x64 con NVIDIA y CUDA 13.0.

En particular, ese lock fija `ultralytics==8.4.146`, versión utilizada en las
evidencias experimentales del entorno Windows/CUDA. La instalación genérica
mediante `pyproject.toml` no fija esa versión: una prueba limpia en CPU resolvió
`ultralytics==8.4.166` y completó la suite con 126 pruebas aprobadas y 2
omitidas. No se reinterpretan por ello los resultados históricos.

El entorno fijado puede reconstruirse como referencia de OP-59 con:

```powershell
.\engine\.venv\Scripts\python.exe -m pip install --requirement .\engine\requirements.windows-cu130.lock.txt
.\engine\.venv\Scripts\python.exe -m pip install --no-deps --editable .\engine
```

Un entorno futuro, como macOS con MPS, podrá incorporar su propio archivo lock después de ser validado. El lock de Windows no reemplaza `pyproject.toml` ni define compatibilidad universal del motor.

## Licencia

El código fuente propio del Operix académico se distribuye bajo
**AGPL-3.0-or-later**; véase el [LICENSE](../LICENSE) del repositorio.
La biblioteca Ultralytics utilizada para YOLO11 y su implementación de ByteTrack
declara **AGPL-3.0** y conserva su propia titularidad y política de licencia;
véanse los [avisos de terceros](../THIRD_PARTY_NOTICES.md). Operix no reclama
titularidad sobre Ultralytics ni ByteTrack.

## Procesamiento de video grabado

OP-33 incorpora una fuente de video grabada que valida el archivo, obtiene sus propiedades y entrega sus frames secuencialmente. Toda la lógica de lectura y control de recursos reside en `operix_engine.video_processor`; el script es solo una interfaz CLI.

Desde la raíz del repositorio:

```powershell
.\engine\.venv\Scripts\python.exe .\engine\scripts\process_video.py <ruta-al-video>
```

La salida incluye resolución, FPS y frames declarados por OpenCV, duración estimada, frames efectivamente procesados y tiempo total. Una diferencia entre el total declarado y el leído genera una advertencia cuando corresponde, ya que el contenedor y el backend pueden informar valores aproximados.

Pruebas automatizadas:

```powershell
.\engine\.venv\Scripts\python.exe -m unittest discover -s .\engine\tests -v
```

Las pruebas generan un AVI/MJPEG sintético en un directorio temporal. En las
ejecuciones originales los videos de entrada se conservaron fuera de Git;
posteriormente se incorporaron **solo** dos entradas sintéticas verificadas y
una salida anotada en [`assets/demo/`](../assets/demo/README.md). Los demás videos
y las salidas nuevas de ejecución deben permanecer fuera del repositorio.

Las pruebas de integración real con YOLO11/ByteTrack son optativas: utilizan
`OPERIX_YOLO11_WEIGHTS`, `OPERIX_OP18_VIDEO` y `OPERIX_OP35_VIDEO` cuando se
proporcionan rutas locales válidas; sin ellas, `unittest` las omite. La suite
restante no necesita descargar pesos.

## Detección de objetos

OP-34 incorpora un contrato propio que transforma cada frame BGR `uint8` en una tupla
inmutable de detecciones. `operix_engine.detection` define los tipos y el contrato;
`operix_engine.yolo_detector` adapta YOLO11 sin exponer objetos internos de Ultralytics.

El detector recibe una ruta local de pesos y nunca descarga pesos implícitamente. El
script `engine/scripts/detect_video.py` coordina la fuente de OP-33, el detector y los
artefactos diagnósticos de validación. El índice del frame permanece fuera de
`Detection`. El adaptador no abre videos, no realiza tracking, no aplica reglas y no
dibuja visualizaciones.

La línea base experimental es YOLO11n con pesos COCO: archivo exacto
`yolo11n.pt`, SHA-256 del experimento
`0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1`.
Los pesos no están en Git. Ultralytics documenta que su API puede obtener
automáticamente los pesos oficiales en el primer uso de `YOLO("yolo11n.pt")`;
esa obtención debe hacerse **por separado**, verificar el hash y pasar después
la ruta local al detector de Operix. El detector y los scripts de este proyecto
no descargan pesos implícitamente. Véase [OP-34](evidence/OP-34-yolo11-detection.md)
y la [documentación oficial de YOLO11](https://github.com/ultralytics/yolo11).
COCO contiene la clase `person`,
pero no contiene una clase `forklift`; `truck` no se reinterpreta como montacargas.

## Seguimiento multiobjeto

OP-35 incorpora ByteTrack detrás de tipos propios de Operix. El tracker recibe una
tupla de `Detection` por cada frame y devuelve una tupla inmutable de `Track` con ID
temporal, clase observada, confianza y caja. No recibe imágenes ni expone objetos
internos de Ultralytics.

El orquestador debe llamar al tracker exactamente una vez por frame, incluso si no
hay detecciones, y reiniciarlo al comenzar cada video. Las trayectorias se reconstruyen
externamente agrupando los centros de las cajas por `track_id`; no forman parte del
estado público de `Track`. Los IDs solo son válidos dentro de una sesión y no
identifican personas.

## Visualización técnica

OP-60 incorpora un renderer OpenCV reutilizable para anotar copias de frames con
cajas, clase, confianza, IDs temporales y trayectorias. El renderer recibe únicamente
`Detection`, `Track` y trayectorias propias de Operix; no abre videos, ejecuta modelos,
actualiza el tracker ni escribe archivos.

`TrajectoryAccumulator` mantiene fuera de `Track` un historial acotado por ID. Los
puntos incluyen el índice del frame, por lo que las pérdidas se muestran como cortes
de trayectoria y no como desplazamientos observados. Los scripts continúan siendo
responsables de la orquestación y de escribir nuevos videos diagnósticos fuera del
repositorio; las tres copias revisadas de `assets/demo/` son la excepción.

## Medición de rendimiento

OP-43 incorpora instrumentación reproducible con `time.perf_counter_ns()` para medir
lectura OpenCV, inferencia YOLO11, ByteTrack, visualización, escritura y tiempo total.
La inferencia CUDA se sincroniza antes y después de cada medición. El warm-up queda
fuera de las estadísticas y la finalización de `VideoWriter` se registra separada de
la latencia por frame.

El escenario A representa el **pipeline base de procesamiento**, no todos los
componentes futuros del Motor. El FPS principal se calcula como frames medidos sobre
tiempo acumulado; no como promedio de FPS instantáneos. Los resultados describen el
equipo, muestra y configuración documentados y no constituyen un umbral universal de
tiempo real.

## PoC técnico integrado

OP-61 reutiliza `scripts/track_video.py` para ejecutar los 277 frames de `ceiling_04`
con YOLO11n-COCO, filtro `person`, ByteTrack, trayectorias y video anotado. La ejecución
local del 21/09/2026 produjo 1.088 detecciones, 644 observaciones y 8 IDs temporales.
La suite completa aprobó 55/55 pruebas con ambas integraciones reales habilitadas.

El [informe OP-61](evidence/OP-61-poc.md) incluye el comando reproducible con todos
los argumentos obligatorios, verificaciones previas, ficha del entorno y revisión
visual. El [resumen JSON](evidence/OP-61-poc-summary.json) conserva trazabilidad sin
rutas privadas. En la ejecución histórica, pesos, video de entrada y salidas,
JSONL por frame, capturas y logs estaban fuera de Git. Más tarde se incorporaron
las dos entradas verificadas y una copia del video anotado en
[`assets/demo/`](../assets/demo/README.md); **solo esos tres MP4** son excepciones.
Pesos, JSONL y nuevas salidas siguen fuera del repositorio; cada ejecución debe
usar destinos nuevos para no sobrescribir evidencia.

Las métricas A/B/C se reutilizan de OP-43. Su escenario C no incluye escritura JSONL,
por lo que sus FPS no se atribuyen directamente a la ejecución integrada de OP-61.
COCO no contiene `forklift`; persisten pérdidas, duplicaciones y fragmentación del
tracking. El PoC no acredita cobertura completa del dominio ni tiempo real sostenido.

## Configuración operacional (OP-30)

El ejemplo `config/examples/op30-zone-rule.json` declara una vista, zonas con
coordenadas normalizadas y parámetros de regla. Puede cargarse con
`operix_engine.operational_config.load_operational_config(path)`; el módulo valida
la estructura y devuelve `Zone`, `RuleConfig` y `OperationalConfig` sin depender
del detector, tracker ni renderer. `schema_version` es `1` y el único sistema de
coordenadas admitido es `normalized`. Cambiar parámetros en el JSON no modifica
el código de percepción. La prueba geométrica de zonas y la evaluación de reglas
se implementaron en OP-36 y OP-38, respectivamente; OP-37 proporciona las
variables descriptivas de pertenencia y permanencia.

## Regla configurable inicial (OP-38)

`RuleEngine` consume `FrameSpatialState` de OP-37 y el `RuleConfig` de OP-30.
La primera regla `zone_dwell` exige clase y zona configuradas, pertenencia y
`dwell_time_s >= min_duration_s`. Emite un `EventCandidate` en memoria solo al
pasar de falso a verdadero. Gaps, ausencias y salidas rearman la condición;
una configuración nueva inicia una instancia/sesión nueva. El umbral de 2 s del
ejemplo es experimental, no universal. Véase la [evidencia OP-38](evidence/OP-38-rules.md).

## Componentes de arquitectura

Estos siete componentes conceptuales pertenecen al mismo motor; no son servicios independientes. Procesamiento, detección, seguimiento, análisis espacio-temporal, configuración y evaluación inicial de reglas están implementados. El gestor/persistencia de eventos sigue pendiente:

1. Procesador de video.
2. Detector de objetos.
3. Seguimiento multiobjeto.
4. Analizador espacio-temporal.
5. Gestor de configuración.
6. Motor de reglas.
7. Gestor de eventos.

## Estado

OP-59 estableció el entorno reproducible, OP-33 incorporó el procesamiento secuencial
de video grabado, OP-34 integró YOLO11 y OP-35 integró ByteTrack. OP-60 incorpora la
visualización técnica reutilizable. OP-43 instrumenta FPS y latencia del pipeline
vigente sin optimizarlo.

OP-61 consolidó la ejecución integrada y sus evidencias y quedó cerrada; ese PoC
no incorporó reglas, zonas, proximidad ni eventos. Posteriormente
OP-30, OP-36 y OP-37 añadieron configuración, pertenencia y variables descriptivas;
OP-38 incorpora evaluación inicial de reglas y candidatos en memoria.
Persistencia OP-39, backend y frontend siguen pendientes.

Consulte el [índice de arquitectura](../docs/architecture/README.md) para los artefactos vigentes.
