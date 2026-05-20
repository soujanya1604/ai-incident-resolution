# Deploy on AWS (EC2 + CloudFormation)

One EC2 instance runs FastAPI (localhost:8001), Streamlit (localhost:8501), and nginx (public port 80).

## Prerequisites

1. **AWS account** with permissions for EC2, CloudFormation, IAM.
2. **AWS CLI** installed and configured:
   ```bash
   brew install awscli    # macOS
   aws configure          # Access key, secret, region (e.g. us-east-1)
   ```
3. **EC2 key pair** in your target region (EC2 → Key pairs → Create).
4. **OpenAI API key**.

## Quick deploy (from your laptop)

```bash
cd deploy/aws
chmod +x deploy.sh scripts/bootstrap.sh
export AWS_REGION=us-east-1
export KEY_PAIR=your-key-pair-name
export OPENAI_API_KEY=sk-...
export SSH_CIDR=YOUR_IP/32    # recommended
./deploy.sh
```

Or interactively (script prompts for key pair and API key).

## After deploy

1. Wait **10–20 minutes** for bootstrap (`pip install` + first API warmup).
2. SSH and tail logs:
   ```bash
   ssh -i ~/your-key.pem ubuntu@PUBLIC_IP
   sudo tail -f /var/log/ai-incident-bootstrap.log
   ```
3. Open **http://PUBLIC_IP** in a browser.
4. Verify services:
   ```bash
   curl http://127.0.0.1:8001/health
   sudo systemctl status ai-incident-api ai-incident-ui nginx
   ```

## HTTPS (optional)

Point a domain A record to the instance public IP, then on the server:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d incident.yourdomain.com
```

Open port **443** in the CloudFormation security group (or add manually in EC2 console).

## Tear down

```bash
aws cloudformation delete-stack --stack-name ai-incident-resolution --region us-east-1
```

## Security notes

- API (8001) and Streamlit (8501) bind to **127.0.0.1** only.
- Only ports **22**, **80** (and **443** if you add TLS) are public.
- `OpenAIApiKey` is passed via EC2 user-data (visible to anyone with EC2 read access in the account). For production, use Secrets Manager + SSM instead.

## Manual deploy (no CloudFormation)

See the main project README or use `scripts/bootstrap.sh` on an existing Ubuntu 22.04 EC2 instance:

```bash
export OPENAI_API_KEY=sk-...
export REPO_URL=https://github.com/soujanya1604/ai-incident-resolution.git
sudo -E bash deploy/aws/scripts/bootstrap.sh
```
