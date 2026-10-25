# 1. Deployment manifest — gcs-reader.yaml 
Replace YOUR_BUCKET_NAME and YOUR_PROJECT_ID with your values.

# 2. Configure GKE Workload Identity Federation 
Run these commands from a terminal with gcloud and kubectl configured. 

    PROJECT_ID="scalkit"
    NAMESPACE="default"
    KSA="gcs-reader-ksa"
    GSA="gcs-reader"

    gcloud services enable iam.googleapis.com \
    storage.googleapis.com \
    --project="$PROJECT_ID"

    gcloud iam service-accounts create "$GSA" \
    --project="$PROJECT_ID"

Grant the Kubernetes service account permission to impersonate the Google service account: 

    gcloud iam service-accounts add-iam-policy-binding \
    "$GSA@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/iam.workloadIdentityUser" \
    --member="serviceAccount:$PROJECT_ID.svc.id.goog[$NAMESPACE/$KSA]" \
    --project="$PROJECT_ID"

Annotate the Kubernetes service account: 

    kubectl annotate serviceaccount "$KSA" \
    -n "$NAMESPACE" \
    iam.gke.io/gcp-service-account="$GSA@$PROJECT_ID.iam.gserviceaccount.com" 

Ensure Workload Identity Federation is enabled for your GKE cluster and node pool. For GKE Autopilot, it is enabled by default.

# 3. Grant read-only access to the GCS bucket 

gcloud storage buckets add-iam-policy-binding \
  gs://gcs-bhoopesh-demo \
  --member="serviceAccount:gcs-reader@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"

roles/storage.objectViewer allows reading objects and listing objects. If you require access only to this specific file, use a bucket IAM condition or an object-level IAM policy where supported.  

# 4. Deploy and validate  

    kubectl apply -f gcs-reader.yaml

    kubectl rollout status deployment/gcs-reader

    kubectl logs deployment/gcs-reader

Expected output:

    ===== sample_data.txt =====
    This is sample data from GCS
    ===== End of file =====