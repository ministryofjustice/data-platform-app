#!/usr/bin/env bash

set -euo pipefail

echo "Logging in to AWS"
aws-sso login

echo "Retrieving AI Gateway License"
AI_GATEWAY_LICENSE=$(aws-sso exec --profile data-platform-development:platform-engineer-admin -- aws secretsmanager get-secret-value --secret-id ai-gateway/litellm-license --query SecretString --output text)
export AI_GATEWAY_LICENSE

echo "Starting AI Gateway"
docker compose --file contrib/docker-compose-ai-gateway.yml up --detach

echo "Waiting for AI Gateway to start"
until curl --silent --fail http://localhost:4000/health/liveliness; do
  sleep 5
done

echo "Seeding AI Gateway Organisation"
curl \
  --silent \
  --fail-with-body \
  --show-error \
  --request POST \
  --url "http://localhost:4000/organization/new" \
  --header "Content-Type: application/json" \
  --header "Authorization: Bearer sk-123456789" \
  --data '{
    "organization_id": "ministry-of-justice",
    "organization_alias": "Ministry of Justice",
    "models": ["all-proxy-models"]
  }'

echo "Seeding AI Gateway Models"
curl \
  --silent \
  --fail-with-body \
  --show-error \
  --request POST \
  --url "http://localhost:4000/model/new" \
  --header "Content-Type: application/json" \
  --header "Authorization: Bearer sk-123456789" \
  --data '{
    "model_name": "bedrock-claude-sonnet-5",
    "litellm_params": {
      "model": "bedrock/eu.anthropic.claude-sonnet-5",
      "ai_model_provider": "Amazon Bedrock",
      "ai_model_name": "Anthropic Claude Sonnet 5 (EU)",
      "ai_model_generally_available": true
    },
    "model_info": {}
  }'

curl \
  --silent \
  --fail-with-body \
  --show-error \
  --request POST \
  --url "http://localhost:4000/model/new" \
  --header "Content-Type: application/json" \
  --header "Authorization: Bearer sk-123456789" \
  --data '{
    "model_name": "bedrock-claude-opus-4-8",
    "litellm_params": {
      "model": "bedrock/eu.anthropic.claude-opus-4-8",
      "ai_model_provider": "Amazon Bedrock",
      "ai_model_name": "Anthropic Claude Opus 4.8 (EU)",
      "ai_model_generally_available": false
    },
    "model_info": {}
  }'

echo "Seeding AI Gateway Unified Access Group"
curl \
  --silent \
  --fail-with-body \
  --show-error \
  --request POST \
  --url "http://localhost:4000/v1/unified_access_group" \
  --header "Content-Type: application/json" \
  --header "Authorization: Bearer sk-123456789" \
  --data '{
    "access_group_name": "generally-available-models",
    "access_model_names": ["bedrock-claude-sonnet-5"]
  }'
