# OP-59 — Entorno reproducible del motor

Fecha de validación: 2026-09-10

Rama: `dev`

## Configuración validada

| Elemento | Resultado |
| --- | --- |
| Sistema | Windows 10 x64 |
| Python | 3.12.10, AMD64, 64 bits |
| GPU | NVIDIA GeForce RTX 3070, 8192 MiB |
| Driver NVIDIA | 616.56 |
| Capacidad de cómputo | 8.6 |
| PyTorch | 2.14.0+cu130 |
| TorchVision | 0.29.0+cu130 |
| Runtime CUDA incluido | 13.0 |
| OpenCV | 5.0.0 |
| Ultralytics | 8.4.146 |
| operix-engine | 0.1.0, instalación editable |

PyTorch y TorchVision se instalaron previamente desde el índice oficial `cu130`. Las dependencias comunes se instalaron después desde `engine/pyproject.toml`. No se instaló CUDA Toolkit ni `nvcc`.

`pyproject.toml` es la fuente principal de dependencias comunes. PyTorch y TorchVision se resuelven previamente según la plataforma. `requirements.windows-cu130.lock.txt` conserva las versiones exactas de este entorno Windows/NVIDIA validado y no representa una definición universal del motor. Futuros entornos, incluido macOS/MPS, podrán generar su propio lock después de validarse.

El lock se generó desde `.venv` con `pip freeze --all --exclude-editable`. Se excluyó `operix-engine` por ser una instalación editable local y se incorporó el índice oficial `cu130` requerido para reconstruir las variantes de PyTorch.

## Comando de verificación

```powershell
.\engine\.venv\Scripts\python.exe .\engine\scripts\check_environment.py --require-cuda
```

## Resultado

```text
Operix OP-59 - verificacion de entorno
Python: 3.12.10 (64bit)
Sistema: Windows 10 (AMD64)
PyTorch: 2.14.0+cu130
TorchVision: 0.29.0+cu130
OpenCV: 5.0.0
Ultralytics: 8.4.146
operix-engine: 0.1.0
CUDA compilado en PyTorch: 13.0
CUDA disponible: True
MPS disponible: False
Dispositivo seleccionado: cuda
GPU: NVIDIA GeForce RTX 3070
Capacidad de computo: (8, 6)
Prueba tensor CPU: OK (checksum=45.0)
Prueba tensor CUDA: OK (checksum=45.0)
Prueba OpenCV: OK
```

`pip check` informó `No broken requirements found.`

El archivo congelado fue revisado para confirmar que no contiene rutas locales, referencias a `.venv` ni la distribución editable `operix-engine`.

SHA-256 histórico de `requirements.windows-cu130.lock.txt`, registrado para el entorno originalmente validado y cerrado en OP-59: `9CF79EB856297F76131651C221DD0E92E6373452E4E3A8DC407DFF0D7119229F`.

Este hash se conserva como evidencia histórica; no identifica el lock actual. Posteriormente, OP-35 incorporó explícitamente `lap==0.5.12` para ByteTrack, tanto en `pyproject.toml` como en el lock Windows/CUDA. Esa incorporación fue la única adición al lock y no cambió ninguna versión previamente fijada. Véase [la evidencia de OP-35](OP-35-bytetrack.md).

## Compatibilidad y límites

- La selección automática se define como `CUDA → MPS → CPU`.
- CUDA y CPU quedaron validados mediante operaciones reales de tensores.
- MPS no está disponible en Windows; su validación queda pendiente para un equipo Apple Silicon.
- El lanzador `py` instalado previamente no detectó Python 3.12. El entorno se creó correctamente con la ruta explícita del intérprete instalado por WinGet.
- Ultralytics crea un archivo de configuración al importarse. El verificador lo dirige dentro de `.venv`, que está excluido de Git.
- No se descargaron pesos de YOLO11 ni se procesaron videos.

## Licencia de dependencia

Ultralytics se distribuye bajo licencia AGPL-3.0. La consideración queda registrada para una evaluación posterior de distribución, sin introducir cambios en Operix Architecture v1.0.
