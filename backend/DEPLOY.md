# Deployment (AWS)

How the backend runs for the demo: one EC2 instance serving the API over HTTPS, PostgreSQL on RDS, and menu photos in S3. Region: Seoul (`ap-northeast-2`).

```text
[Android app] --HTTPS--> [EC2: Caddy :443 -> uvicorn 127.0.0.1:8000 (systemd)]
                              |-- instance role --> [S3: menu photos, private; presigned URLs]
                              |-- security group -> [RDS PostgreSQL, no public access]
```

| Resource | Name |
| --- | --- |
| Domain | `bottlemap.o-r.kr` (free domain from 내도메인.한국) |
| S3 bucket | `bottlemap-menu-photos` |
| IAM role (EC2 instance profile) | `bottlemap-ec2-role`, inline policy `bottlemap-s3-photos` |
| EC2 instance / security group | `bottlemap-api` / `bottlemap-ec2` |
| RDS instance / database / user | `bottlemap-db` / `bottlemap` / `bottlemap` |

Files used on the server are in [`deploy/`](deploy/): the systemd service, the Caddyfile, `env.production.example`, and `deploy.sh`.

Never commit or paste secrets (the RDS password, `TEMP_AUTH_JWT_SECRET`, `GEMINI_API_KEY`); they live only in `backend/.env` on the server. The deploy key for automatic deployment lives only in GitHub secrets.

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
   - New security group `bottlemap-ec2`: SSH (22) from **my IP** only, HTTP (80) and HTTPS (443) from anywhere. Port 80 is needed for the certificate. Automatic deployment later opens SSH to anywhere (section 5).
   - Advanced details → IAM instance profile: `bottlemap-ec2-role`.
5. **Elastic IP**: EC2 → Elastic IPs → allocate, then associate it with `bottlemap-api`.
6. **DNS**: at 내도메인.한국, set the A record of `bottlemap.o-r.kr` to the Elastic IP. Check with `nslookup bottlemap.o-r.kr` until it returns the IP.
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
curl http://127.0.0.1:8000/health          # {"status":"ok","version":"<commit>"}
```

The server refuses to start when a setting is missing (e.g. `IMAGE_STORAGE=s3` without `S3_BUCKET`); `journalctl -u bottlemap-api -n 50` shows why.

**HTTPS.**

```sh
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
journalctl -u caddy -f                     # wait for "certificate obtained successfully"
```

## 3. Check

From your PC, with `BASE=https://bottlemap.o-r.kr`:

- `curl $BASE/health` returns `{"status":"ok","version":"<commit>"}`, and `$BASE/docs` opens Swagger UI.
- The full flow, as in the [README](README.md#menu-import-upload-review-publish):
  1. `POST $BASE/api/auth/temp-login` for an operator token; `GET $BASE/api/bars` for a bar id.
  2. Upload a photo named `sample.jpg` to that bar, then poll `GET $BASE/api/menu-imports/<id>` until `ready_for_review`.
  3. `imageUrl` is an `https://bottlemap-menu-photos.s3.ap-northeast-2.amazonaws.com/...` presigned URL that opens, and `imageUrlExpiresAt` is about 15 minutes later. The object appears in the S3 console under `menus/<barId>/<menuImportId>/`.
  4. Submit `review-and-apply`; the new menu shows in `GET $BASE/api/bars/<barId>/menu` and customer search.
- `sudo reboot`, wait a minute, and check `/health` again: both services start by themselves.
- In the Android app, set the base URL to `https://bottlemap.o-r.kr`.

Afterwards, reset the demo data (next paragraph).

**Reset the demo data** after a rehearsal, so the demo starts from the freshly seeded state. On the server, while nobody is uploading:

```sh
cd ~/swpp-2026-project-team-19/backend
uv run --no-sync --env-file .env python scripts/reset_demo.py            # shows what would be deleted
uv run --no-sync --env-file .env python scripts/reset_demo.py --apply
```

It deletes every menu import with its photos in S3, every menu board, and the bars, brands, products, and aliases added after seeding, then seeds the catalog and the Seorosang menu again. The first line of its output names the database, so check that it is RDS.

## 4. Redeploy

Pushes to `main` are deployed automatically once section 5 is set up. To deploy by hand (another branch, or before that setup), run on the server:

```sh
~/swpp-2026-project-team-19/backend/deploy/deploy.sh          # current branch
~/swpp-2026-project-team-19/backend/deploy/deploy.sh main     # switch branch first
```

It pulls, runs `uv sync --frozen --no-dev` and the migrations, restarts the service, and waits for `/health`; on failure it prints the last log lines.

## 5. Automatic deployment (GitHub Actions)

When a push to `main` changes the backend, the **Backend CI/CD** workflow (`.github/workflows/backend-ci-cd.yml`) runs the tests. If they pass, its `deploy` job connects over SSH, runs `deploy.sh main`, and checks from outside that `https://bottlemap.o-r.kr/health` reports the commit it deployed (`version`). Pull requests only run the tests. A deployment can also be started from the Actions tab (Backend CI/CD → Run workflow on `main`); it runs the tests first as well.

Deployments run one at a time, and a running one is never cancelled. Each deploys the latest `main`.

### One-time setup

1. **Deploy key.** On your PC, create a key used only by GitHub Actions, without a passphrase:

   ```sh
   ssh-keygen -t ed25519 -N "" -C bottlemap-deploy -f bottlemap-deploy
   ```

   This writes `bottlemap-deploy` (private) and `bottlemap-deploy.pub` (public).

2. **Allow the key on the server, for `deploy.sh` only.** Add the public key to `~/.ssh/authorized_keys` with options in front:

   ```sh
   printf 'restrict,command="/home/ubuntu/swpp-2026-project-team-19/backend/deploy/deploy.sh main" %s\n' \
     "$(cat bottlemap-deploy.pub)" | ssh -i bottlemap-key.pem ubuntu@bottlemap.o-r.kr 'cat >> ~/.ssh/authorized_keys'
   ```

   - `command=` makes every connection with this key run `deploy.sh main`, whatever command the client sends.
   - `restrict` turns off terminals and port forwarding.
   - A leaked deploy key can therefore only redeploy `main`.
   - Check it: `ssh -i bottlemap-deploy ubuntu@bottlemap.o-r.kr ls` runs a deployment instead of `ls`.

3. **Host key.** Get the server's host key line, and check that its fingerprint matches the one the server reports over your usual SSH session:

   ```sh
   ssh-keyscan -t ed25519 bottlemap.o-r.kr                             # the line for the secret
   ssh-keyscan -t ed25519 bottlemap.o-r.kr | ssh-keygen -lf -          # its fingerprint
   ssh -i bottlemap-key.pem ubuntu@bottlemap.o-r.kr 'ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub'
   ```

   The workflow refuses to connect when the server answers with any other key. A new EC2 instance has a new host key, so update the secret then.

4. **GitHub secrets.** Settings → Environments → New environment `production` → Environment secrets:

   | Secret | Value |
   | --- | --- |
   | `DEPLOY_SSH_KEY` | The whole private key file `bottlemap-deploy`, including the `BEGIN` and `END` lines |
   | `DEPLOY_KNOWN_HOSTS` | The `bottlemap.o-r.kr ssh-ed25519 AAAA...` line from step 3 |

   Only the `deploy` job, which declares the `production` environment, can read them. After saving, delete the local private key; GitHub is the only place that needs it.

5. **Security group.** GitHub-hosted runners connect from changing addresses, so `bottlemap-ec2` must allow SSH (22) from anywhere (`0.0.0.0/0`). Password login is off on Ubuntu EC2 images, so only the two keys in `authorized_keys` can log in, and the deploy key can only run `deploy.sh`.

### When a deployment fails

- Open the failed run → `deploy` → **Run deploy.sh on the server**. It shows the output of `deploy.sh`, including the last 50 service log lines when `/health` does not come up.
- To roll back, revert the commit on `main` (`git revert <commit>`) and push. The revert is tested and deployed like any other change.
- To pause automatic deployment, remove the deploy key line from `authorized_keys`. Deploy jobs then fail at SSH; the tests still run.

## 6. Operations

- **Logs:** `journalctl -u bottlemap-api -f` (API), `journalctl -u caddy -f` (HTTPS, proxy).
- **Settings:** edit `backend/.env`, then `sudo systemctl restart bottlemap-api`.
- **Real extraction:** set `MENU_EXTRACTOR=gemini` and `GEMINI_API_KEY` (a paid-tier key, so uploaded menu photos are not used for training) and restart. The settings are checked at start-up.
- **Temporary login** is on for the demo, so anyone who reaches the server can get an operator token. Keep the server running only when needed, and set `TEMP_AUTH_ENABLED=false` when the demo period ends.
- **Known limitation:** an import that is `processing` when the service restarts stays there; delete it with `reset_menu_imports.py` and upload again.
- **Cost:** stop the EC2 and RDS instances when idle. A stopped RDS instance starts again by itself after 7 days, and the Elastic IP is billed while the instance is stopped.

## 7. Teardown

When the project ends: delete the RDS instance (and any snapshots), terminate the EC2 instance, release the Elastic IP, empty and delete the S3 bucket, delete the IAM role and the `bottlemap-*` security groups, remove the DNS record, and delete the `production` environment (with its deploy key) on GitHub.
