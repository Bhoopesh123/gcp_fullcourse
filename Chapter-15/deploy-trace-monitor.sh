#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

: "${GCP_PROJECT_ID:?GCP_PROJECT_ID is required}"
: "${GCP_REGION:?GCP_REGION is required}"
: "${DT_URL:?DT_URL is required}"

EVALUATOR_ID="${TRACE_EVALUATOR_ID:-132574714030718976}"
SERVICE_NAME="${TRACE_SERVICE_NAME:-agent-trace-eval-to-dynatrace}"
TOPIC_NAME="${TRACE_TOPIC_NAME:-agent-trace-evaluation-logs}"
SUBSCRIPTION_NAME="${TRACE_SUBSCRIPTION_NAME:-agent-trace-eval-to-dynatrace}"
SINK_NAME="${TRACE_SINK_NAME:-agent-trace-evaluation-logs}"
PUSH_SA_NAME="${TRACE_PUSH_SA_NAME:-agent-trace-dt-push}"
PUSH_SA="${PUSH_SA_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
RUNTIME_SA="agent-eval-dt-runtime@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
SECRET_NAME="agent-evaluation-to-dynatrace-platform-token"
LOG_FILTER="resource.type=\"aiplatform.googleapis.com/OnlineEvaluator\" AND resource.labels.location=\"${GCP_REGION}\" AND resource.labels.online_evaluator_id=\"${EVALUATOR_ID}\" AND labels.\"event.name\"=\"gen_ai.evaluation.result\" AND jsonPayload.candidateResult.score>=0"

gcloud config set project "${GCP_PROJECT_ID}" >/dev/null

gcloud pubsub topics describe "${TOPIC_NAME}" >/dev/null 2>&1 || \
  gcloud pubsub topics create "${TOPIC_NAME}"

gcloud iam service-accounts describe "${PUSH_SA}" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "${PUSH_SA_NAME}"

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
  --timeout=60 \
  --quiet

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --region "${GCP_REGION}" --format='value(status.url)')"
gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --region "${GCP_REGION}" \
  --member="serviceAccount:${PUSH_SA}" \
  --role=roles/run.invoker >/dev/null

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
    --description="Trace evaluation metrics forwarded to Dynatrace"
fi

SINK_WRITER="$(gcloud logging sinks describe "${SINK_NAME}" --format='value(writerIdentity)')"
gcloud pubsub topics add-iam-policy-binding "${TOPIC_NAME}" \
  --member="${SINK_WRITER}" \
  --role=roles/pubsub.publisher >/dev/null

echo "Trace monitor deployment complete"
echo "Evaluator: ${EVALUATOR_ID}"
echo "Cloud Run: ${SERVICE_URL}"
echo "Topic: projects/${GCP_PROJECT_ID}/topics/${TOPIC_NAME}"
echo "Subscription: ${SUBSCRIPTION_NAME}"
echo "Sink: ${SINK_NAME}"
