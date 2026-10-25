FROM python:3.12.10-slim-bookworm AS opencv-wheel
# El wheel público no incluye un encoder H.264 usable: misma versión, FFmpeg del sistema.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake ninja-build pkg-config git \
    libavcodec-dev libavformat-dev libavutil-dev libswscale-dev \
    && rm -rf /var/lib/apt/lists/*
ENV CMAKE_BUILD_PARALLEL_LEVEL=4 \
    CMAKE_ARGS="-DWITH_FFMPEG=ON -DWITH_QT=OFF -DWITH_GTK=OFF -DWITH_IPP=OFF -DWITH_ITT=OFF -DBUILD_TESTS=OFF -DBUILD_PERF_TESTS=OFF -DBUILD_JAVA=OFF"
RUN python -m pip wheel --no-deps --no-binary opencv-python --wheel-dir /wheels opencv-python==5.0.0.93
COPY deployment/docker/codec_smoke.py /codec_smoke.py
RUN python -m pip install numpy==2.5.2 /wheels/*.whl && python /codec_smoke.py

FROM python:3.12.10-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    YOLO_AUTOINSTALL=false YOLO_CONFIG_DIR=/var/lib/operix/cache \
    TMPDIR=/var/lib/operix/sessions
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 libavcodec59 libavformat59 libavutil57 libswscale6 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=opencv-wheel /wheels /wheels
COPY engine/requirements.windows-cu130.lock.txt /app/engine/requirements.windows-cu130.lock.txt
COPY backend/requirements.txt /app/backend/requirements.txt
# Pins existentes sin cambios; pip añade las dependencias CUDA específicas de Linux del wheel.
RUN python -m pip install /wheels/*.whl \
    && python -m pip install -r engine/requirements.windows-cu130.lock.txt -r backend/requirements.txt \
    && python -m pip check && rm -rf /wheels
COPY deployment/docker/requirements.linux-cu130.lock.txt /app/deployment/docker/requirements.linux-cu130.lock.txt
RUN python -m pip install --no-deps -r /app/deployment/docker/requirements.linux-cu130.lock.txt \
    && python -m pip check
COPY engine/pyproject.toml engine/README.md /app/engine/
COPY engine/src /app/engine/src
COPY engine/scripts /app/engine/scripts
COPY engine/config /app/engine/config
RUN python -m pip install --no-deps -e /app/engine
COPY backend /app/backend
COPY deployment/docker/backend_start.py /app/deployment/docker/backend_start.py
COPY deployment/docker/codec_smoke.py /app/deployment/docker/codec_smoke.py
COPY LICENSE THIRD_PARTY_NOTICES.md /app/
RUN groupadd --gid 10001 operix && useradd --uid 10001 --gid operix --no-create-home operix \
    && mkdir -p /var/lib/operix/media /var/lib/operix/sessions /var/lib/operix/cache \
    && chown -R operix:operix /var/lib/operix
RUN python /app/deployment/docker/codec_smoke.py
USER operix
WORKDIR /app/backend
EXPOSE 8000
CMD ["python", "/app/deployment/docker/backend_start.py"]
