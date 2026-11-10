#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Copy .env.example to .env and fill it in." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

required=(GCP_PROJECT_ID GCP_REGION LOG_FILTER DT_URL DT_PLATFORM_TOKEN)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required value: ${name}" >&2
    exit 1
  fi
done

SERVICE_NAME="${SERVICE_NAME:-agent-evaluation-to-dynatrace}"
TOPIC_NAME="${TOPIC_NAME:-agent-evaluation-logs}"
SUBSCRIPTION_NAME="${SUBSCRIPTION_NAME:-agent-evaluation-to-dynatrace}"
SINK_NAME="${SINK_NAME:-agent-evaluation-logs}"
# IAM service-account IDs have a hard 30-character limit. Keep these stable and
# independent of the potentially longer Cloud Run service name.
RUNTIME_SA_NAME="agent-eval-dt-runtime"
PUSH_SA_NAME="agent-eval-dt-push"
SECRET_NAME="${SERVICE_NAME}-platform-token"
RUNTIME_SA="${RUNTIME_SA_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
PUSH_SA="${PUSH_SA_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project "${GCP_PROJECT_ID}" >/dev/null
gcloud services enable \
  run.googleapis.com pubsub.googleapis.com logging.googleapis.com \
  secretmanager.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

gcloud pubsub topics describe "${TOPIC_NAME}" >/dev/null 2>&1 || \
  gcloud pubsub topics create "${TOPIC_NAME}"

for sa_name in "${RUNTIME_SA_NAME}" "${PUSH_SA_NAME}"; do
  gcloud iam service-accounts describe "${sa_name}@${GCP_PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1 || \
    gcloud iam service-accounts create "${sa_name}"
done

gcloud secrets describe "${SECRET_NAME}" >/dev/null 2>&1 || \
  gcloud secrets create "${SECRET_NAME}" --replication-policy=automatic
printf '%s' "${DT_PLATFORM_TOKEN}" | gcloud secrets versions add "${SECRET_NAME}" --data-file=-

gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role=roles/secretmanager.secretAccessor >/dev/null

gcloud run deploy "${SERVICE_NAME}" \
  --source "${ROOT_DIR}/app" \
  --region "${GCP_REGION}" \
  --service-account "${RUNTIME_SA}" \
  --no-allow-unauthenticated \
  --set-env-vars="DT_URL=${DT_URL}" \
  --set-secrets="DT_PLATFORM_TOKEN=${SECRET_NAME}:latest" \
  --min-instances=0 \
  --max-instances=10 \
  --concurrency=20 \
  --timeout=60

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --region "${GCP_REGION}" --format='value(status.url)')"
gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --region "${GCP_REGION}" \
  --member="serviceAccount:${PUSH_SA}" \
  --role=roles/run.invoker >/dev/null

# Pub/Sub's service agent must be able to mint an OIDC token as PUSH_SA.
PROJECT_NUMBER="$(gcloud projects describe "${GCP_PROJECT_ID}" --format='value(projectNumber)')"
PUBSUB_SERVICE_AGENT="service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"
gcloud iam service-accounts add-iam-policy-binding "${PUSH_SA}" \
  --member="serviceAccount:${PUBSUB_SERVICE_AGENT}" \
  --role=roles/iam.serviceAccountTokenCreator >/dev/null

if gcloud pubsub subscriptions describe "${SUBSCRIPTION_NAME}" >/dev/null 2>&1; then
  gcloud pubsub subscriptions update "${SUBSCRIPTION_NAME}" \
    --push-endpoint="${SERVICE_URL}/" \
    --push-auth-service-account="${PUSH_SA}" \
    --push-auth-token-audience="${SERVICE_URL}" \
    --min-retry-delay=10s --max-retry-delay=600s
else
  gcloud pubsub subscriptions create "${SUBSCRIPTION_NAME}" \
    --topic="${TOPIC_NAME}" \
    --push-endpoint="${SERVICE_URL}/" \
    --push-auth-service-account="${PUSH_SA}" \
    --push-auth-token-audience="${SERVICE_URL}" \
    --ack-deadline=60 \
    --message-retention-duration=7d \
    --min-retry-delay=10s --max-retry-delay=600s
fi

DESTINATION="pubsub.googleapis.com/projects/${GCP_PROJECT_ID}/topics/${TOPIC_NAME}"
if gcloud logging sinks describe "${SINK_NAME}" >/dev/null 2>&1; then
  gcloud logging sinks update "${SINK_NAME}" "${DESTINATION}" --log-filter="${LOG_FILTER}"
else
  gcloud logging sinks create "${SINK_NAME}" "${DESTINATION}" \
    --log-filter="${LOG_FILTER}" \
    --description="Agent evaluation results forwarded to Dynatrace"
fi

SINK_WRITER="$(gcloud logging sinks describe "${SINK_NAME}" --format='value(writerIdentity)')"
gcloud pubsub topics add-iam-policy-binding "${TOPIC_NAME}" \
  --member="${SINK_WRITER}" \
  --role=roles/pubsub.publisher >/dev/null

echo "Deployment complete"
echo "Cloud Run: ${SERVICE_URL}"
echo "Topic: projects/${GCP_PROJECT_ID}/topics/${TOPIC_NAME}"
echo "Sink: ${SINK_NAME}"
