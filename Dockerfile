# Score Before You Sign on LinuxONE (#11).
# On the VM, build FROM the hackathon lab image (TF + zDNN plugin + XGBoost + llama.cpp):
#   docker build --build-arg BASE=<lab image> -t sbys .
# Anywhere else, the default base is enough for the API and pages.
ARG BASE=python:3.12-slim
FROM ${BASE}

WORKDIR /app
# The lab image's Python is a venv at /opt/venv owned by its non-root ibm-user, so a plain install works there too
RUN pip install --no-cache-dir fastapi==0.115.6 uvicorn==0.32.1
COPY *.py ./
COPY static/ static/
COPY models/ models/
# data/ is a volume (snapshot + payee memory), and the key arrives via --env-file: neither is baked in.
EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
