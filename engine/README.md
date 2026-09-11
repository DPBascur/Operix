# Motor de análisis de video

Componente de Operix Architecture v1.0 que transforma video en resultados de análisis y eventos de interés preventivo.

> La IA percibe el entorno; las reglas interpretan el contexto.

Flujo conceptual: video → detección → tracking → variables espacio-temporales → reglas configurables → evento → Backend/API → registro/histórico.

## Tecnologías y límites

- Python 3.12 x64 y OpenCV para procesamiento de video.
- YOLO11 para detección y ByteTrack para seguimiento, como selecciones iniciales y experimentales.
- Configuración recibida desde el Backend/API; resultados entregados al Backend/API.
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
.\engine\.venv\Scripts\python.exe .\engine\scripts\check_environment.py --require-cuda
```

El mecanismo de selección de dispositivo sigue el orden `CUDA → MPS → CPU`. En el entorno Windows actual se validan mediante operaciones reales de tensores tanto CUDA como CPU.

El verificador dirige la configuración que Ultralytics crea al importarse hacia `.venv`, evitando generar archivos locales sin seguimiento en la raíz del repositorio. No descarga pesos ni procesa videos.

### Entorno congelado validado

`pyproject.toml` mantiene las dependencias comunes del proyecto. PyTorch y TorchVision se instalan primero con la distribución correspondiente a cada plataforma.

`requirements.windows-cu130.lock.txt` registra exclusivamente las versiones exactas del entorno probado en Windows x64 con NVIDIA y CUDA 13.0. Puede reconstruirse como referencia de OP-59 con:

```powershell
.\engine\.venv\Scripts\python.exe -m pip install --requirement .\engine\requirements.windows-cu130.lock.txt
.\engine\.venv\Scripts\python.exe -m pip install --no-deps --editable .\engine
```

Un entorno futuro, como macOS con MPS, podrá incorporar su propio archivo lock después de ser validado. El lock de Windows no reemplaza `pyproject.toml` ni define compatibilidad universal del motor.

## Consideración de licencia

Ultralytics se distribuye bajo licencia AGPL-3.0. Esta condición queda registrada para evaluar sus implicaciones antes de una eventual decisión de distribución; no modifica Operix Architecture v1.0.

## Módulos internos futuros

Estos siete componentes conceptuales pertenecen al mismo motor; no son servicios independientes:

1. Procesador de video.
2. Detector de objetos.
3. Seguimiento multiobjeto.
4. Analizador espacio-temporal.
5. Gestor de configuración.
6. Motor de reglas.
7. Gestor de eventos.

## Estado

Entorno reproducible en preparación mediante OP-59. El primer PoC previsto es video → OpenCV → YOLO11 → ByteTrack → visualización de detecciones/tracks → métricas FPS/latencia. Aportará evidencia técnica inicial para RF-01, RF-02, RF-03 y RNF-02; todavía no está implementado.

Consulte el [índice de arquitectura](../docs/architecture/README.md) para los artefactos vigentes.
