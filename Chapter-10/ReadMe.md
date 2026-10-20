# AI Agent Deployment steps on GKE

# 1. Create GKE cluster with Autopilot Mode (Google manages the nodes for you)

    gcloud container clusters create-auto first-autopilot-cluster \
     --region us-central1 

    gcloud components install gke-gcloud-auth-plugin 

    gcloud container clusters get-credentials first-autopilot-cluster --region us-central1 

    kubectl apply -f petclinic.yaml

# 2. Deploy AI Agent on GKE

    adk deploy gke \
    --project=scalkit \
    --region=us-central1 \
    --cluster_name=first-autopilot-cluster \
    --with_ui \
    --trace_to_cloud \
    --otel_to_cloud \
    my_first_agent  

# 3. Some Misc Commands for Troubleshooting

    gcloud auth login 

    gcloud auth application-default login 

    gcloud projects add-iam-policy-binding scalkit \
    --member="serviceAccount:scalkit.svc.id.goog[default/default]" \
    --role="roles/aiplatform.user"
    
    gcloud projects get-iam-policy scalkit \
    --flatten="bindings[].members" \
    --filter="bindings.role:roles/aiplatform.user" \
    --format="table(bindings.role,bindings.members)"
    
    ROLE: roles/aiplatform.user
    MEMBERS: serviceAccount:scalkit.svc.id.goog[default/default]
