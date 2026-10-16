# AI Agent Deployment steps

# 1. Create AI Agent 

    adk create my_first_agent

# 2. Deploy AI Agent

    adk deploy cloud_run \
    --project=scalkit \
    --region=us-central1 \
    --service_name=adk-mydemo \
    --with_ui \
    --trace_to_cloud \
    --otel_to_cloud \
    --port 8081 \
    my_first_agent

# 3. Check Logs in case of any error during deployment.

    gcloud run services logs read adk-mydemo \
    --project=scalkit \
    --region=us-central1 \
    --limit=50