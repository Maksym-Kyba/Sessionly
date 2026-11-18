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
| `email.env.example` | Template for the backend-only Gmail App Password file kept on the server |
| `scripts/deploy.sh` | Deploys a Git branch to the server and restarts the stack |

## Prerequisites

- An AWS account and a local AWS CLI profile named `sessionly` (or set `aws_profile` in
  `terraform.tfvars`)
- Terraform 1.6 or newer
- An SSH key pair for the server:

  ```bash
  ssh-keygen -t ed25519 -f ~/.ssh/sessionly -C sessionly-deployer
  ```

If you sign in with `aws login --profile sessionly`, the Terraform AWS provider may not read that
session and reports "No valid credential sources found". Export the session's temporary credentials
for the current shell and leave the profile empty:

```bash
eval "$(aws configure export-credentials --profile sessionly --format env)"
terraform plan -var 'aws_profile='
terraform apply -var 'aws_profile='
```

SSH is allowed only from the addresses in `ssh_allowed_cidrs`: canonical IPv4 CIDR blocks,
normally one `/32` per administrator, without duplicates.

### Change an administrator's IP address safely

Never remove the working address first, or the administrator can lock themselves out.

1. Add the new `/32` address to `ssh_allowed_cidrs` in `terraform.tfvars` and keep the old one.
2. Run `terraform plan`, check that it only adds one SSH rule, and run `terraform apply`.
3. Open a new terminal and connect with `ssh -i ~/.ssh/sessionly ubuntu@<public_ip>`.
4. Only after that connection succeeds, remove the old address and apply again.

If no administrator can connect any more, restore access through the AWS Management Console:

1. Open EC2 → Security Groups → `sessionly-web` → Edit inbound rules.
2. Add a rule: type SSH, source "My IP", and save. Connect over SSH to confirm access.
3. Delete that manual rule in the console, add the same address to `terraform.tfvars`, and run
   `terraform apply`, so that Terraform manages the rule again. A manual rule with the same
   address would make the apply fail with a duplicate rule error.

### Migrate from the single `ssh_allowed_cidr` variable

Earlier versions used a single `ssh_allowed_cidr` string and a single SSH rule. The rule is now
created with `for_each`, one instance per address. For each existing Terraform state, before the
next `plan`:

1. In the ignored `terraform.tfvars`, rename `ssh_allowed_cidr = "<cidr>"` to
   `ssh_allowed_cidrs = ["<cidr>"]`.
2. Move the existing rule to its keyed address, so that Terraform does not delete and recreate it:

   ```bash
   terraform state mv 'aws_vpc_security_group_ingress_rule.ssh' \
     'aws_vpc_security_group_ingress_rule.ssh["<cidr>"]'
   ```

3. Run `terraform plan` and check that it does not replace the existing SSH rule.

The demo server's state has already been migrated; do not repeat these steps for it.

## 1. Create the server

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# Set ssh_allowed_cidrs to the public IP address of each administrator, each with /32.
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
2. Create the production environment files on the server from their templates. The Gmail file is
   optional if email delivery is not configured yet; the deploy script installs a blank template
   and the application starts with verification delivery failing closed.

   ```bash
   scp -i ~/.ssh/sessionly infra/.env.example ubuntu@<public_ip>:/opt/sessionly/.env
   scp -i ~/.ssh/sessionly infra/email.env.example ubuntu@<public_ip>:/opt/sessionly/email.env
   ssh -i ~/.ssh/sessionly ubuntu@<public_ip>
   nano /opt/sessionly/.env
   nano /opt/sessionly/email.env
   ```

   Replace every `<domain>` with `site_domain` and fill in the database password, Google OAuth
   credentials and secret keys. For Gmail delivery, set `GMAIL_SMTP_USERNAME` in `.env` and
   `GMAIL_APP_PASSWORD` in `email.env`. Set the App Password
   only in `/opt/sessionly/email.env`; set its permissions with `chmod 600` on both environment
   files. The deploy script copies the Gmail file into `infra/` with mode `600`. Compose injects it
   into the backend container only; the migration and frontend containers do not receive the App
   Password. Neither file is committed.

   Mock payments are disabled by default in production (`APP_ENV=production`). For the controlled
   demo only, add `MOCK_PAYMENTS_ENABLED=true` to `/opt/sessionly/.env` so that clients can pay
   with the mock endpoint; no real money moves. Set it back to `MOCK_PAYMENTS_ENABLED=false` (or
   remove the line) and deploy again after the demo, because while it is enabled any client with a
   booking access token can confirm a booking without paying.

### Gmail demo sender

Use a dedicated Google account for Sessionly rather than a teammate's personal account. Enable
2-Step Verification with an eligible method, then create an App Password labeled for the Sessionly
EC2 server. Some organization-managed accounts, Advanced Protection accounts, and accounts using
only security keys may not offer App Passwords. Use the account's exact Gmail address as
`GMAIL_SMTP_USERNAME` and sender address. Do not use the account's regular password.

The backend connects to `smtp.gmail.com:587` using STARTTLS with certificate validation and a
bounded socket timeout. EC2 restricts outbound SMTP port 25 by default; this deployment uses port
587. Before deploying, verify outbound TLS connectivity from the EC2 host:

```bash
openssl s_client -starttls smtp -connect smtp.gmail.com:587 -crlf
```

Send a verification message to a team-controlled inbox and consume the link in another browser or
device. Gmail is configured for the low-volume demo only. Revoke the App Password after the demo if
it is no longer needed. Google revokes App Passwords when the account password changes, so a
replacement must be configured after such a change.

## 3. Deploy

From the repository root:

```bash
infra/scripts/deploy.sh          # deploys main
infra/scripts/deploy.sh my-branch
```

The script pulls the branch from GitHub on the server, builds the images, applies database
migrations through the `migrate` service and restarts the stack. Run it again for every new
release.

Migrations are only applied forward. Do not run `alembic downgrade` on the production database:
downgrading below revision `20261118_0006` drops the `payments` table and permanently deletes
payment history, including payments awaiting manual review. Treat any downgrade as a deliberate,
approved operation and back up the database first.

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
