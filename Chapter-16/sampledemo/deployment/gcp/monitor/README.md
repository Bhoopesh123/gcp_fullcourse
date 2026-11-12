# Phoenix online monitor CronJob

This is separate from the Streamlit Deployment. Kubernetes CronJob schedules
have one-minute precision, so the job starts every minute and runs bounded
cycles at 0, 20, and 40 seconds.

## Environment mapping

Non-secret values are in `cronjob.yaml`:

- `PHOENIX_PROJECT`
- `PHOENIX_API_URL` (Phoenix HTTP API, not the OTLP collector port)
- `JUDGE_MODEL`
- `JUDGE_SAMPLE_PERCENT`
- `BATCH_SIZE`

Secrets are stored in `phoenix-monitor-secrets`:

- `OPENAI_API_KEY`
- `PHOENIX_API_KEY`
- `DT_PLATFORM_TOKEN`
- `DT_ENV_URL`
- `GRAFANA_LOKI_URL`
- `GRAFANA_LOKI_USER`
- `GRAFANA_LOKI_TOKEN`

## Create the secret from the current `.env`

Run from the repository root. This creates the Secret directly without writing
credentials into a manifest:

```bash
set -a
. ./.env
set +a

kubectl create namespace sampledemo --dry-run=client -o yaml | kubectl apply -f -
kubectl -n sampledemo create secret generic phoenix-monitor-secrets \
  --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY" \
  --from-literal=PHOENIX_API_KEY="$PHOENIX_API_KEY" \
  --from-literal=DT_PLATFORM_TOKEN="$DT_PLATFORM_TOKEN" \
  --from-literal=DT_ENV_URL="$DT_ENV_URL" \
  --from-literal=GRAFANA_LOKI_URL="$GRAFANA_LOKI_URL" \
  --from-literal=GRAFANA_LOKI_USER="$GRAFANA_LOKI_USER" \
  --from-literal=GRAFANA_LOKI_TOKEN="$GRAFANA_LOKI_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -
```

Alternatively, copy `secret.example.yaml` to `secret.yaml`, replace its
placeholders, and apply it. Never commit `secret.yaml`.

## Deploy and verify

```bash
kubectl apply -f deployment/gcp/monitor/cronjob.yaml
kubectl -n sampledemo get cronjob phoenix-online-monitor
kubectl -n sampledemo get jobs --sort-by=.metadata.creationTimestamp
kubectl -n sampledemo logs -l app=phoenix-online-monitor --tail=200
```

Run an immediate test job without waiting for the next minute:

```bash
kubectl -n sampledemo create job \
  --from=cronjob/phoenix-online-monitor \
  phoenix-online-monitor-manual
kubectl -n sampledemo logs -f job/phoenix-online-monitor-manual
```
