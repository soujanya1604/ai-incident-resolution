#!/usr/bin/env bash
# Deploy AI Incident Resolution to AWS EC2 via CloudFormation.
set -euo pipefail

STACK_NAME="${STACK_NAME:-ai-incident-resolution}"
REGION="${AWS_REGION:-us-east-1}"
KEY_PAIR="${KEY_PAIR:-}"
OPENAI_KEY="${OPENAI_API_KEY:-}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.small}"
SSH_CIDR="${SSH_CIDR:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="${SCRIPT_DIR}/cloudformation/ec2-stack.yaml"

if ! command -v aws >/dev/null 2>&1; then
  echo "AWS CLI is not installed."
  echo "  macOS: brew install awscli"
  echo "  Then:  aws configure"
  exit 1
fi

if [[ -z "$KEY_PAIR" ]]; then
  echo "Available key pairs in ${REGION}:"
  aws ec2 describe-key-pairs --region "$REGION" --query 'KeyPairs[*].KeyName' --output table
  read -r -p "Enter KeyPairName: " KEY_PAIR
fi

if [[ -z "$OPENAI_KEY" ]]; then
  read -r -s -p "Enter OPENAI_API_KEY: " OPENAI_KEY
  echo
fi

if [[ -z "$SSH_CIDR" ]]; then
  echo "Tip: restrict SSH to your IP, e.g. $(curl -s https://checkip.amazonaws.com 2>/dev/null || echo 'YOUR_IP')/32"
  read -r -p "SSH allowed CIDR [0.0.0.0/0]: " SSH_CIDR
  SSH_CIDR="${SSH_CIDR:-0.0.0.0/0}"
fi

echo "Deploying stack ${STACK_NAME} in ${REGION}..."
aws cloudformation deploy \
  --region "$REGION" \
  --stack-name "$STACK_NAME" \
  --template-file "$TEMPLATE" \
  --parameter-overrides \
    KeyPairName="$KEY_PAIR" \
    InstanceType="$INSTANCE_TYPE" \
    OpenAIApiKey="$OPENAI_KEY" \
    SSHAllowedCidr="$SSH_CIDR" \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset

echo ""
echo "Stack outputs:"
aws cloudformation describe-stacks \
  --region "$REGION" \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs' \
  --output table

PUBLIC_IP="$(aws cloudformation describe-stacks \
  --region "$REGION" \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='PublicIp'].OutputValue" \
  --output text)"

echo ""
echo "Bootstrap takes 10–20 minutes (pip + embeddings)."
echo "Watch logs: ssh -i YOUR_KEY.pem ubuntu@${PUBLIC_IP} 'sudo tail -f /var/log/ai-incident-bootstrap.log'"
echo "When complete, open: http://${PUBLIC_IP}"
