FROM python:3.12.8-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY analysis /app/analysis
COPY rig /app/rig
COPY schemas /app/schemas
ENV PYTHONPATH=/app:/app/rig:/app/analysis
CMD ["python", "-m", "harness.driver", "--help"]
