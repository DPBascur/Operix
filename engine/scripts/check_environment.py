# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verifica el entorno de ejecucion del motor de Operix para OP-59."""

from __future__ import annotations

import argparse
import os
import platform
import sys
from importlib import metadata
from pathlib import Path


def package_version(distribution: str) -> str:
    """Obtiene la version instalada de una distribucion."""
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "no instalado"


def select_device(torch_module: object) -> str:
    """Selecciona el dispositivo disponible en orden CUDA, MPS y CPU."""
    if torch_module.cuda.is_available():
        return "cuda"

    mps = getattr(torch_module.backends, "mps", None)
    if mps is not None and mps.is_available():
        return "mps"

    return "cpu"


def tensor_test(torch_module: object, device: str) -> tuple[bool, str]:
    """Ejecuta una multiplicacion real de tensores en el dispositivo indicado."""
    try:
        left = torch_module.arange(1, 10, dtype=torch_module.float32, device=device)
        left = left.reshape(3, 3)
        right = torch_module.eye(3, dtype=torch_module.float32, device=device)
        result = left @ right

        if device == "cuda":
            torch_module.cuda.synchronize()

        passed = torch_module.equal(result.cpu(), left.cpu())
        return bool(passed), f"checksum={result.sum().item():.1f}"
    except Exception as error:  # pragma: no cover - informa fallos del entorno
        return False, f"{type(error).__name__}: {error}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-cuda",
        action="store_true",
        help="Falla si CUDA no esta disponible; se usa para validar el equipo NVIDIA.",
    )
    args = parser.parse_args()

    # El chequeo no debe depender de permisos de escritura en el perfil global.
    os.environ.setdefault(
        "YOLO_CONFIG_DIR",
        str(Path(sys.prefix)),
    )

    try:
        import cv2
        import numpy as np
        import torch
        import torchvision
        import ultralytics
    except ImportError as error:
        print(f"ERROR importando dependencias: {error}")
        return 1

    python_supported = sys.version_info[:2] == (3, 12) and platform.architecture()[0] == "64bit"
    cuda_available = torch.cuda.is_available()
    mps_backend = getattr(torch.backends, "mps", None)
    mps_available = bool(mps_backend is not None and mps_backend.is_available())
    selected_device = select_device(torch)

    cpu_ok, cpu_detail = tensor_test(torch, "cpu")
    cuda_ok, cuda_detail = (False, "no disponible")
    if cuda_available:
        cuda_ok, cuda_detail = tensor_test(torch, "cuda")

    try:
        image = np.zeros((2, 2, 3), dtype=np.uint8)
        opencv_ok = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).shape == (2, 2)
    except Exception as error:  # pragma: no cover - informa fallos del entorno
        opencv_ok = False
        print(f"ERROR en prueba OpenCV: {type(error).__name__}: {error}")

    print("Operix OP-59 - verificacion de entorno")
    print(f"Python: {platform.python_version()} ({platform.architecture()[0]})")
    print(f"Sistema: {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"PyTorch: {torch.__version__}")
    print(f"TorchVision: {torchvision.__version__}")
    print(f"OpenCV: {cv2.__version__}")
    print(f"Ultralytics: {ultralytics.__version__}")
    print(f"operix-engine: {package_version('operix-engine')}")
    print(f"CUDA compilado en PyTorch: {torch.version.cuda}")
    print(f"CUDA disponible: {cuda_available}")
    print(f"MPS disponible: {mps_available}")
    print(f"Dispositivo seleccionado: {selected_device}")

    if cuda_available:
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"Capacidad de computo: {torch.cuda.get_device_capability(0)}")

    print(f"Prueba tensor CPU: {'OK' if cpu_ok else 'ERROR'} ({cpu_detail})")
    print(f"Prueba tensor CUDA: {'OK' if cuda_ok else 'NO VALIDADA'} ({cuda_detail})")
    print(f"Prueba OpenCV: {'OK' if opencv_ok else 'ERROR'}")

    checks = [python_supported, cpu_ok, opencv_ok]
    if args.require_cuda:
        checks.append(cuda_available and cuda_ok)

    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
