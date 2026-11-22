ARG BASE_IMAGE=operix-backend:local
FROM ${BASE_IMAGE} AS ort
USER root
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cu13/lib:/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib:/usr/local/nvidia/lib64:/usr/local/nvidia/lib
RUN python -m pip --isolated install --no-cache-dir --no-deps --only-binary=:all: \
    --index-url https://pypi.org/simple onnx==1.19.1 onnxruntime-gpu==1.27.0 \
    protobuf==6.33.6 ml-dtypes==0.5.4 flatbuffers==25.12.19 wheel==0.45.1
USER operix

FROM ort AS ort-live
USER root
RUN cp /app/engine/scripts/run_rtsp_lab.py /app/engine/scripts/_rtsp_pytorch_worker.py
COPY deployment/rtsp-lab/benchmark_rtsp_onnx.py /app/engine/scripts/run_rtsp_lab.py
COPY deployment/rtsp-lab/benchmark_backends.py deployment/rtsp-lab/benchmark_gpu.py /app/rtsp-proof/
COPY --from=exports person.onnx forklift.onnx report.json /experimental-models/
USER operix

FROM ort AS tensorrt
USER root
ENV NVIDIA_TENSORRT_DISABLE_INTERNAL_PIP=1
RUN python -m pip --isolated install --no-cache-dir --no-deps --only-binary=:all: \
    --index-url https://pypi.nvidia.com tensorrt-cu13-bindings==10.13.3.9.post1 \
    tensorrt-cu13-libs==10.13.3.9.post1
RUN python -m pip --isolated install --no-cache-dir --no-deps --no-build-isolation \
    --index-url https://pypi.org/simple tensorrt-cu13==10.13.3.9.post1
USER operix
