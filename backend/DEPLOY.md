# Deployment (AWS)

How the backend runs for the demo: one EC2 instance serving the API over HTTPS, PostgreSQL on RDS, and menu photos in S3. Region: Seoul (`ap-northeast-2`).

```text
[Android app] --HTTPS--> [EC2: Caddy :443 -> uvicorn 127.0.0.1:8000 (systemd)]
                              |-- instance role --> [S3: menu photos, private; presigned URLs]
                              |-- security group -> [RDS PostgreSQL, no public access]
```

| Resource | Name |
| --- | --- |
| Domain | `bottlemap.kro.kr` (free domain from 내도메인.한국) |
| S3 bucket | `bottlemap-menu-photos` |
| IAM role (EC2 instance profile) | `bottlemap-ec2-role`, inline policy `bottlemap-s3-photos` |
| EC2 instance / security group | `bottlemap-api` / `bottlemap-ec2` |
| RDS instance / database / user | `bottlemap-db` / `bottlemap` / `bottlemap` |

Files used on the server are in [`deploy/`](deploy/): the systemd service, the Caddyfile, `env.production.example`, and `deploy.sh`.

Never commit or paste secrets (the RDS password, `TEMP_AUTH_JWT_SECRET`, `GEMINI_API_KEY`); they live only in `backend/.env` on the server.

## 1. AWS resources (console)

1. **Budget alert.** Billing and Cost Management → Budgets → cost budget, e.g. $20/month with e-mail alerts at 50/80/100%. Exclude credits in the advanced options, otherwise spending shows as zero while credits are used up.
2. **S3 bucket** `bottlemap-menu-photos`: general purpose, ACLs disabled, **block all public access**, versioning off, SSE-S3 encryption. No bucket policy or CORS is needed; the app opens photos through presigned URLs.
3. **IAM role** `bottlemap-ec2-role`: trusted entity AWS service → EC2, no managed policies. Add an inline policy `bottlemap-s3-photos`:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
         "Resource": "arn:aws:s3:::bottlemap-menu-photos/*"
       }
     ]
   }
   ```

4. **EC2** `bottlemap-api`:
   - Ubuntu Server 24.04 LTS, a free-tier eligible type (e.g. `t3.micro`), 20 GiB gp3. Keep the key pair `.pem` file safe.
   - New security group `bottlemap-ec2`: SSH (22) from **my IP** only, HTTP (80) and HTTPS (443) from anywhere. Port 80 is needed for the certificate.
   - Advanced details → IAM instance profile: `bottlemap-ec2-role`.
5. **Elastic IP**: EC2 → Elastic IPs → allocate, then associate it with `bottlemap-api`.
6. **DNS**: at 내도메인.한국, set the A record of `bottlemap.kro.kr` to the Elastic IP. Check with `nslookup bottlemap.kro.kr` until it returns the IP.
7. **RDS** `bottlemap-db`: standard create, PostgreSQL (latest available), template **Free tier**, master user `bottlemap` with a self-managed password, `db.t4g.micro` or `db.t3.micro`, gp3 20 GiB with storage autoscaling off.
   - Connectivity: **Connect to an EC2 compute resource** → `bottlemap-api`. This sets up the security groups and keeps public access off.
   - Additional configuration → **Initial database name: `bottlemap`**.
   - Creation takes about 10–15 minutes. Note the endpoint (Connectivity & security tab).

## 2. Server setup (SSH)

```sh
chmod 400 bottlemap-key.pem
ssh -i bottlemap-key.pem ubuntu@<elastic-ip>
```

**Swap and packages.** A small instance needs swap for `uv sync`.

```sh
sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
sudo apt update && sudo apt install -y git curl caddy postgresql-client
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env
```

**Code and settings.** Use `main`, or the branch being tested before it is merged (`git checkout <branch>`).

```sh
git clone https://github.com/snuhcs-course/swpp-2026-project-team-19.git
cd ~/swpp-2026-project-team-19/backend
cp deploy/env.production.example .env && chmod 600 .env
openssl rand -hex 32      # paste as TEMP_AUTH_JWT_SECRET
nano .env                 # POSTGRES_HOST (RDS endpoint), POSTGRES_PASSWORD, TEMP_AUTH_JWT_SECRET
```

`.env` must stay plain `KEY=VALUE` lines: systemd reads it too and takes everything after `=` literally, comments included.

**Dependencies, database, seed data.**

```sh
uv sync --frozen --no-dev
uv run --no-sync --env-file .env alembic upgrade head
uv run --no-sync --env-file .env python scripts/seed_catalog.py
uv run --no-sync --env-file .env python scripts/seed_menu.py
```

If the connection fails, check the RDS endpoint and password, and that the RDS security group allows the EC2 one. To connect directly: `psql "host=<endpoint> user=bottlemap dbname=bottlemap sslmode=require"`.

**API service.**

```sh
sudo cp deploy/bottlemap-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bottlemap-api
curl http://127.0.0.1:8000/health          # {"status":"ok"}
```

The server refuses to start when a setting is missing (e.g. `IMAGE_STORAGE=s3` without `S3_BUCKET`); `journalctl -u bottlemap-api -n 50` shows why.

**HTTPS.**

```sh
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
journalctl -u caddy -f                     # wait for "certificate obtained successfully"
```

If Let's Encrypt refuses the domain (for example a rate limit on the shared `kro.kr` suffix), replace `bottlemap.kro.kr` in `/etc/caddy/Caddyfile` with `<elastic-ip-with-dashes>.sslip.io` (e.g. `3-35-10-20.sslip.io`) and reload; the app then uses that host.

## 3. Check

From your PC, with `BASE=https://bottlemap.kro.kr`:

- `curl $BASE/health` returns `{"status":"ok"}`, and `$BASE/docs` opens Swagger UI.
- The full flow, as in the [README](README.md#menu-import-upload-review-publish):
  1. `POST $BASE/api/auth/temp-login` for an operator token; `GET $BASE/api/bars` for a bar id.
  2. Upload a photo named `sample.jpg` to that bar, then poll `GET $BASE/api/menu-imports/<id>` until `ready_for_review`.
  3. `imageUrl` is an `https://bottlemap-menu-photos.s3.ap-northeast-2.amazonaws.com/...` presigned URL that opens, and `imageUrlExpiresAt` is about 15 minutes later. The object appears in the S3 console under `menus/<barId>/<menuImportId>/`.
  4. Submit `review-and-apply`; the new menu shows in `GET $BASE/api/bars/<barId>/menu` and customer search.
- `sudo reboot`, wait a minute, and check `/health` again: both services start by themselves.
- In the Android app, set the base URL to `https://bottlemap.kro.kr`.

Afterwards, restore the demo menu with `seed_menu.py`, and remove test imports that were never applied with `scripts/reset_menu_imports.py`.

## 4. Redeploy

```sh
~/swpp-2026-project-team-19/backend/deploy/deploy.sh          # current branch
~/swpp-2026-project-team-19/backend/deploy/deploy.sh main     # switch branch first
```

It pulls, runs `uv sync --frozen --no-dev` and the migrations, restarts the service, and waits for `/health`; on failure it prints the last log lines.

## 5. Operations

- **Logs:** `journalctl -u bottlemap-api -f` (API), `journalctl -u caddy -f` (HTTPS, proxy).
- **Settings:** edit `backend/.env`, then `sudo systemctl restart bottlemap-api`.
- **Real extraction:** set `MENU_EXTRACTOR=gemini` and `GEMINI_API_KEY` (a paid-tier key, so uploaded menu photos are not used for training) and restart. The settings are checked at start-up.
- **Temporary login** is on for the demo, so anyone who reaches the server can get an operator token. Keep the server running only when needed, and set `TEMP_AUTH_ENABLED=false` when the demo period ends.
- **Known limitation:** an import that is `processing` when the service restarts stays there; delete it with `reset_menu_imports.py` and upload again.
- **Cost:** stop the EC2 and RDS instances when idle. A stopped RDS instance starts again by itself after 7 days, and the Elastic IP is billed while the instance is stopped.

## 6. Teardown

When the project ends: delete the RDS instance (and any snapshots), terminate the EC2 instance, release the Elastic IP, empty and delete the S3 bucket, delete the IAM role and the `bottlemap-*` security groups, and remove the DNS record.
