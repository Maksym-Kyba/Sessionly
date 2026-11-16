# Sessionly Deployment

Sessionly runs on a single AWS EC2 instance. Terraform creates the server, and Docker Compose runs
the whole application on it. Caddy obtains a free Let's Encrypt certificate and serves everything
over HTTPS from one origin.

```
Browser ──HTTPS──▶ Caddy ──┬── /api/*, /health ──▶ backend (FastAPI) ──▶ db (PostgreSQL)
                           └── everything else  ──▶ frontend (Next.js)
```

The site uses a free `sslip.io` hostname derived from the server's IP address (for example
`3-120-45-67.sslip.io`), so no domain purchase is required.

## Contents

| Path | Purpose |
|---|---|
| `terraform/` | EC2 instance (Ubuntu 24.04, `t3.small`), Elastic IP, security group, SSH key pair |
| `terraform/user-data.sh` | First-boot setup: swap, Docker, Docker Compose, Git |
| `docker-compose.prod.yml` | Production services: `db`, `migrate`, `backend`, `frontend`, `caddy` |
| `Caddyfile` | HTTPS and routing between the frontend and the backend |
| `.env.example` | Template for the production environment file kept on the server |
| `scripts/deploy.sh` | Deploys a Git branch to the server and restarts the stack |

## Prerequisites

- An AWS account and a local AWS CLI profile named `sessionly` (or set `aws_profile` in
  `terraform.tfvars`)
- Terraform 1.6 or newer
- An SSH key pair for the server:

  ```bash
  ssh-keygen -t ed25519 -f ~/.ssh/sessionly -C sessionly-deployer
  ```

## 1. Create the server

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# Set ssh_allowed_cidr to your public IP address with /32.
# Your current address: curl -s https://checkip.amazonaws.com
terraform init
terraform plan
terraform apply
```

Terraform prints `public_ip`, `site_domain` and `ssh_command`. Wait one or two minutes after the
first apply so that `user-data.sh` can finish installing Docker.

Terraform state is stored locally in `infra/terraform/` and is not committed. The person who
created the infrastructure keeps it; without it, Terraform cannot update or destroy the resources.

## 2. Configure the application

1. In Google Cloud Console, add the redirect URI
   `https://<site_domain>/api/v1/auth/google/callback` to the OAuth web client.
2. Create the production environment file on the server from the template:

   ```bash
   scp -i ~/.ssh/sessionly infra/.env.example ubuntu@<public_ip>:/opt/sessionly/.env
   ssh -i ~/.ssh/sessionly ubuntu@<public_ip>
   nano /opt/sessionly/.env
   ```

   Replace every `<domain>` with `site_domain` and fill in the database password, Google OAuth
   credentials and secret keys. The file stays on the server and is never committed.

## 3. Deploy

From the repository root:

```bash
infra/scripts/deploy.sh          # deploys main
infra/scripts/deploy.sh my-branch
```

The script pulls the branch from GitHub on the server, builds the images, applies database
migrations through the `migrate` service and restarts the stack. Run it again for every new
release.

Check the deployment:

```bash
curl https://<site_domain>/health   # {"status":"ok","database":"ok"}
```

## Costs and teardown

The server, its 20 GiB disk and the public IPv4 address cost roughly USD 20–25 per month in
`eu-north-1`. Remove every resource when it is no longer needed:

```bash
cd infra/terraform
terraform destroy
```

This permanently deletes the server together with its database.
