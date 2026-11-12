FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /monitor

RUN addgroup --system monitor && adduser --system --ingroup monitor monitor

COPY deployment/gcp/monitor/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY phoenix_online_monitor.py export_evaluations_to_dynatrace.py ./

USER monitor

ENTRYPOINT ["python", "phoenix_online_monitor.py"]
