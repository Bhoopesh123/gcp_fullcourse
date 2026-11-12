# Separate GCP/GKE deployment

These assets deploy only the Streamlit application. They do not include or
modify the local Phoenix monitor, Dynatrace forwarder, `.env`, logs, or PID
files.

## 1. Build and push

Run from the repository root:

```bash
export IMAGE="gcr.io/scalkit/sampledemo-streamlit:20261111"
gcloud auth configure-docker gcr.io
docker build -f deployment/gcp/Dockerfile -t "$IMAGE" .
docker push "$IMAGE"
```

## 2. Connect kubectl to GKE

```bash
gcloud container clusters list --project scalkit
gcloud container clusters get-credentials CLUSTER_NAME \
  --location CLUSTER_LOCATION \
  --project scalkit
```

## 3. Create the application secret

Create the secret directly from environment values; do not commit them:

```bash
kubectl create namespace sampledemo --dry-run=client -o yaml | kubectl apply -f -
kubectl -n sampledemo create secret generic sampledemo-secrets \
  --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY" \
  --from-literal=PHOENIX_API_KEY="$PHOENIX_API_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -
```

## 4. Configure and deploy

Replace `REPLACE_WITH_PHOENIX_OTLP_GRPC_ENDPOINT` in `kubernetes.yaml`, then:

```bash
kubectl apply -f deployment/gcp/kubernetes.yaml
kubectl -n sampledemo rollout status deployment/sampledemo-streamlit
kubectl -n sampledemo get service sampledemo-streamlit
```

## 5. Verify or remove

```bash
kubectl -n sampledemo get pods
kubectl -n sampledemo logs deployment/sampledemo-streamlit
kubectl -n sampledemo port-forward service/sampledemo-streamlit 8501:80
```

Open `http://127.0.0.1:8501`. To remove this separate deployment:

```bash
kubectl delete namespace sampledemo
```
