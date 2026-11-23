# Extend the current Backend + Motor image with the same runtime as the CUDA proof.
ARG BASE_IMAGE=operix-backend:local
FROM ${BASE_IMAGE}
USER root
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cu13/lib:/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib:/usr/local/nvidia/lib64:/usr/local/nvidia/lib
RUN python -m pip --isolated install --no-cache-dir --no-deps --only-binary=:all: \
    --index-url https://pypi.org/simple onnx==1.19.1 onnxruntime-gpu==1.27.0 \
    protobuf==6.33.6 ml-dtypes==0.5.4 flatbuffers==25.12.19 wheel==0.45.1
RUN python -m pip check
COPY engine/scripts/run_rtsp_lab.py engine/scripts/rtsp_lab_onnx.py /app/engine/scripts/
COPY deployment/rtsp-lab/benchmark_backends.py deployment/rtsp-lab/benchmark_gpu.py /app/deployment/rtsp-lab/
USER operix
RUN python /app/engine/scripts/run_rtsp_lab.py --help > /dev/null
