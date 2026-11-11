# Deploy Study Companion on Oracle Cloud Always Free

This stack runs the existing FastAPI app in Docker, keeps SQLite and uploads on a
persistent volume, and uses Caddy for automatic HTTPS.

## What you need

- An Oracle Cloud account (Always Free eligible).
- An SSH key pair for the VM.
- A domain name, or a free wildcard DNS name such as `203-0-113-10.sslip.io`
  that resolves to your VM's public IP.
- This repository cloned on the VM.

## 1. Create the VM

In the Oracle Cloud console:

1. **Compute → Instances → Create instance**.
2. Choose an Always Free eligible shape:
   - `VM.Standard.E2.1.Micro` (AMD, small and usually available), or
   - `VM.Standard.A1.Flex` (Arm, faster, but capacity varies by region).
3. Choose **Ubuntu 24.04** or **Ubuntu 22.04**.
4. Upload or select your SSH public key.
5. Create the instance and note its **public IP address**.

If you use the 1 GB AMD micro shape, add swap before building the image:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 2. Open the network ports

In the instance's **VCN → Security List**, add ingress rules for:

- TCP `22` from your IP only
- TCP `80` from `0.0.0.0/0`
- TCP `443` from `0.0.0.0/0`

If the OS firewall is active, allow the same ports:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80,443/tcp
sudo ufw enable
```

On Oracle Linux, use `firewall-cmd` instead.

## 3. Install Docker

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker "$USER"
newgrp docker
```

Check:

```bash
docker compose version
```

## 4. Clone and configure

```bash
git clone https://github.com/Mbongeni3533/Study-Companion.git
cd Study-Companion/deploy/oracle-cloud
cp .env.example .env
```

Generate the two required secrets:

```bash
openssl rand -hex 32
openssl rand -hex 24
```

Put the first value in `JWT_SECRET` and the second in `BETA_ADMIN_KEY` inside
`.env`. Set `DEPLOY_DOMAIN` to your domain or `sslip.io` hostname.

Example:

```dotenv
DEPLOY_DOMAIN=study.example.com
JWT_SECRET=...
BETA_ADMIN_KEY=...
BETA_INVITE_ONLY=true
ALLOW_ANONYMOUS_SESSIONS=false
```

Do not commit `.env`.

## 5. Start the app

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f app
```

Wait for the app health check to pass, then check Caddy:

```bash
docker compose logs -f caddy
```

## 6. Point DNS and get HTTPS

Create an `A` record for `DEPLOY_DOMAIN` pointing at the VM's public IP. Caddy
will obtain and renew the certificate automatically once DNS resolves.

Without a domain, use an `sslip.io` hostname built from the public IP:

```dotenv
DEPLOY_DOMAIN=203-0-113-10.sslip.io
```

Then restart Caddy:

```bash
docker compose up -d
```

## 7. Verify

```bash
curl https://YOUR_DOMAIN/health
```

Expected:

```json
{"status":"ok","app":"Study Companion API","version":"0.2.0","ai_provider":"rules","database":"ok"}
```

Open:

```text
https://YOUR_DOMAIN/
https://YOUR_DOMAIN/admin
```

Use `BETA_ADMIN_KEY` on the admin page to create invitation links, then send
them to the beta group.

## Updates

```bash
cd Study-Companion
git pull
cd deploy/oracle-cloud
docker compose up -d --build
```

## Back up the data volume

```bash
cd Study-Companion/deploy/oracle-cloud
docker run --rm \
  -v study_companion_data:/data \
  -v "$PWD:/backup" \
  alpine sh -c 'tar czf /backup/study-companion-data-$(date +%F).tgz -C /data .'
```

Copy the backup off the VM regularly. The volume contains the SQLite database,
uploads and any generated files.

## Notes

- The app runs as a non-root user inside the container.
- `DATA_DIR=/app/data` is mounted from the `study_companion_data` volume.
- Caddy stores certificates in `study_companion_caddy_data`.
- The Oracle Always Free allowance is enough for a small beta, but capacity and
  limits can change. Check your tenancy's **Limits, Quotas and Usage** page.
- The `Dockerfile` installs Tesseract for OCR. The first build takes several
  minutes, especially on the smallest VM.
