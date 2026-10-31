# Student Management System: Docker, GitHub Actions, Docker Hub, AWS EC2

A Flask + SQLite student records app with a full CI/CD pipeline and a separate monitoring dashboard.

**Status of this project:** the code, unit tests (20 passing), YAML files and shell-script syntax were checked locally. The Docker image build, Docker Hub push, EC2 deployment and live GitHub API calls were **not** run by the author because they need your accounts and credentials. Follow the test checklist (section 12) to verify them yourself.

## 1. Architecture in simple words

```
You (VS Code) --git push--> GitHub --> GitHub Actions
                                          |  1 Validate  2 Test  3 Build image  4 Push to Docker Hub
                                          v
                                     Docker Hub  <--- EC2 pulls image tagged with the commit SHA
                                          |
AWS EC2 (Ubuntu) ------------------------+
  +- nginx      (port 80, public)  --> app (Gunicorn + Flask, private port 8000) --> SQLite in Docker volume
  +- dashboard  (port 8081, password + restricted IP) --> reads GitHub Actions API, checks app health
```

* **app**: the Student Management System. Only Nginx can reach it.
* **nginx**: the public entry point (port 80).
* **dashboard**: a separate container using the same image but a different command, so it stays up when the student app is down. It calls the GitHub API from the *server* so the token never reaches the browser.
* **student_data volume**: holds `students.db`, so data survives container replacement.
* Every image is tagged with the full Git commit SHA. The app reports that SHA at `/api/health`, which is how the dashboard and the pipeline know which version is really running.

```
app/            Flask app (routes, db, templates, static)      dashboard/   monitoring dashboard
tests/          pytest tests                                   nginx/       reverse proxy config
deploy/         setup-ec2.sh deploy.sh rollback.sh backup.sh restore.sh
.github/workflows/ci-cd.yml    Dockerfile  docker-compose.yml  .env.example
```

## 2. Run locally

**Windows PowerShell** (Docker Desktop installed and running):
```powershell
cd student-management-system
Copy-Item .env.example .env
# edit .env: set HTTP_PORT=8080 and DASHBOARD_PASSWORD (notepad .env)
docker compose up -d --build
Start-Process http://localhost:8080
```
Without Docker:
```powershell
python -m venv venv; .\venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest -v
$env:DATABASE_PATH="data\students.db"; flask --app wsgi run --port 5000
```

**Linux / Ubuntu:**
```bash
cp .env.example .env && nano .env       # set HTTP_PORT=8080 and DASHBOARD_PASSWORD
docker compose up -d --build
python3 -m venv venv && . venv/bin/activate && pip install -r requirements-dev.txt && pytest -v
```

Local URLs: app `http://localhost:8080`, dashboard `http://localhost:8081` (user `admin`, password from `.env`).

## 3. Docker commands

```bash
docker compose build                     # build images
docker compose up -d                     # start
docker compose up -d --build             # rebuild after code changes
docker compose ps                        # list containers (shows health)
docker compose logs -f app               # follow logs (also: nginx, dashboard)
docker compose restart app               # restart one service
docker compose stop                      # stop (data kept)
docker compose down                      # remove containers (volume kept; 'down -v' DELETES data)
docker inspect --format '{{.State.Health.Status}}' student-app
docker compose exec app sh               # shell inside the container
```

**Persistence and permissions.** The database is `/data/students.db` inside the container, on the named volume `student_data`. The image creates `/data` owned by the non-root user (uid 1000), and Docker copies that ownership into a new empty volume. SQLite uses WAL mode, so you will also see `-wal`/`-shm` files; never copy only the `.db` file of a running app, use the backup script instead.

**Backup / restore** (run in the deployment directory):
```bash
./deploy/backup.sh                               # creates backups/students-<time>.db (SQLite backup API, safe while running)
./deploy/restore.sh backups/students-<time>.db   # makes a safety backup, replaces the DB, restarts the app
```
Copy backups off the server regularly (`scp`, or `aws s3 cp backups/ s3://your-bucket/ --recursive`). Example daily cron: `0 2 * * * cd /opt/student-management && ./deploy/backup.sh`.

## 4. Docker Hub setup

1. Create an account at hub.docker.com, then **Create repository** named `student-management-system` (private is fine).
2. **Account Settings > Personal access tokens > Generate**, with **Read & Write** access. Copy it once. This is `DOCKERHUB_TOKEN`; never use your password.
3. Manual test:
```bash
docker login -u YOUR_USERNAME                      # paste the token
docker build --build-arg GIT_SHA=manual1 -t YOUR_USERNAME/student-management-system:manual1 .
docker push YOUR_USERNAME/student-management-system:manual1
docker pull YOUR_USERNAME/student-management-system:manual1
```

## 5. GitHub setup

1. Create a repository and push this project (the `.gitignore` keeps `.env` and keys out):
```bash
git init && git add . && git commit -m "Initial commit"
git branch -M main && git remote add origin https://github.com/YOU/REPO.git && git push -u origin main
```
2. **Settings > Secrets and variables > Actions > Secrets**:

| Secret | Value |
|---|---|
| `DOCKERHUB_USERNAME` | your Docker Hub username |
| `DOCKERHUB_TOKEN` | the access token from step 4 |
| `EC2_HOST` | EC2 public IP or DNS name |
| `EC2_USER` | `ubuntu` |
| `EC2_SSH_KEY` | full contents of the private `.pem` key (including BEGIN/END lines) |

3. **Variables** (optional): `IMAGE_REPO` (defaults to `<DOCKERHUB_USERNAME>/student-management-system`), `DEPLOY_DIR` (default `/opt/student-management`), `APP_PUBLIC_URL` (e.g. `https://example.com` once HTTPS is set up), `MAIN_BRANCH` (default `main`; if you use another branch also edit the `branches:` lists at the top of the workflow).

Behaviour: pull requests only validate, test and build (no push, no deploy, no secrets used). Pushes to `main` publish `:<sha>` and `:latest`, then deploy. If the EC2 secrets are missing, the pipeline still validates, tests, builds and pushes; the deploy stage is skipped with a warning.

## 6. AWS EC2 setup

1. Launch **Ubuntu 24.04** (t3.micro/t2.micro is enough), create a key pair, and attach a security group:

| Port | Source | Why |
|---|---|---|
| 22 (SSH) | **your IP only** | administration. GitHub-hosted runners use changing IPs; if SSH from your IP only blocks the pipeline, use a self-hosted runner, or temporarily open 22 knowing the risk (key-only login). |
| 80 (HTTP) | 0.0.0.0/0 | public access through Nginx |
| 443 (HTTPS) | 0.0.0.0/0 | only once you add a domain + certificate |
| 8081 | **your IP only** | dashboard (password protected) |

Port 8000 is never opened: the app container is only reachable by Nginx, and the Docker daemon is not exposed.

2. Install Docker (from your computer, in the project folder):
```bash
ssh -i key.pem ubuntu@EC2_IP 'bash -s' < deploy/setup-ec2.sh
ssh -i key.pem ubuntu@EC2_IP "docker --version && docker compose version"   # reconnect so the docker group applies
```
3. Create the server `.env` once (the pipeline copies everything else):
```bash
scp -i key.pem .env.example ubuntu@EC2_IP:/opt/student-management/.env
ssh -i key.pem ubuntu@EC2_IP "nano /opt/student-management/.env"
```
Set `IMAGE_REPO`, `HTTP_PORT=80`, `GITHUB_REPO`, `GITHUB_TOKEN` (fine-grained token, only this repo, **Actions: read** and **Metadata: read**), and a long random `DASHBOARD_PASSWORD`. Then `chmod 600 /opt/student-management/.env`.
4. Push to `main`. The workflow copies the compose/Nginx/deploy files, logs the server into Docker Hub, pulls the exact SHA image, replaces the containers, waits for the container health check, and then verifies `http://EC2_HOST/api/health` reports that SHA.

**Rollback.** `deploy.sh` remembers the previous tag (`.previous_tag`) and rolls back automatically if the new container is not healthy; the workflow rolls back too if the external health check fails. Manual rollback: `ssh ... "cd /opt/student-management && ./deploy/rollback.sh"`. Or deploy any tag: `IMAGE_REPO=user/student-management-system ./deploy/deploy.sh <sha>`. History is in `deployments.log`.

**HTTPS.** Basic auth on the dashboard sends the password in clear text over plain HTTP, so keep port 8081 restricted to your IP or use an SSH tunnel (`ssh -L 8081:localhost:8081 ...`). For public HTTPS, point a domain at the instance and add a certificate (for example Certbot or an AWS load balancer with ACM), then set the `APP_PUBLIC_URL` variable.

**Server troubleshooting:**
```bash
cd /opt/student-management
docker compose ps ; docker compose logs --tail 100 app ; cat deployments.log
curl -s localhost/api/health ; docker inspect --format '{{json .State.Health}}' student-app
sudo ss -tlnp | grep -E ':80|:8081'          # is the port listening?
```

## 7. The dashboard

Open `http://EC2_IP:8081`. It shows overview cards, every run (branch, commit, trigger, times, duration, GitHub status, link), the seven-stage pipeline (green success, red failed, blue running, grey pending/skipped, dashed = cannot be determined), image/deploy results, failure investigation with troubleshooting tips, filters, auto-refresh every 20 s and a Refresh button.

* Data is real GitHub Actions data; nothing is simulated. Stages come from job and step names listed in `dashboard/stages.py`. **If you rename a job or step in the workflow, update that mapping**, or the stage will show "Unknown".
* The "Latest image tag" is derived from a run whose push step succeeded (the tag convention is the commit SHA). The "Deployed image" is shown only when the running app reports its version at `/api/health`.
* Failure messages come from GitHub check-run annotations (short, truncated). Full logs are deliberately not downloaded; the link opens them on GitHub. Responses are cached server-side (about 20 s; finished runs are cached permanently) to respect rate limits, and on API errors the last good data is shown with a warning.
* Run counts are the repository-wide totals; the detailed list shows the latest 20 runs.

## 8. Security notes

* Secrets live only in GitHub Secrets and the server `.env` (mode 600); `.env`, keys and databases are excluded by `.gitignore` and `.dockerignore`.
* Workflow permissions are `contents: read`; PRs never push or deploy; Docker Hub token instead of password.
* Container runs as non-root; no secrets in the image; the image holds only a version label.
* Gunicorn's access log omits query strings, so search terms (student names) are not logged. The app never logs record contents.
* SSH host keys are fetched with `ssh-keyscan` on each run. For stricter security, store your server's host key in a secret and write it to `known_hosts` instead.
* Actions are pinned to major versions; for higher assurance pin them to commit SHAs.

## 9. API

`GET /api/health` · `GET /api/students?q=` · `POST /api/students` · `GET|PUT|DELETE /api/students/<id>` · `GET /api/stats`. Fields: `name`, `email`, `course`, `semester` (1 to 12); responses include `id` and `created_at`. Validation errors return HTTP 400 with an `errors` object; duplicate emails return 409.

## 10. Common problems

| Symptom | Likely cause / fix |
|---|---|
| Push step fails with "denied" | wrong token permission or repository name; token needs Read & Write |
| Deploy step: `Permission denied (publickey)` | `EC2_SSH_KEY` incomplete or `EC2_USER` wrong |
| Deploy step: timeout | security group blocks port 22 from GitHub runners |
| Health check fails but containers run | port 80 not open in the security group, or `APP_PUBLIC_URL` wrong |
| Dashboard says 404/403 from GitHub | wrong `GITHUB_REPO` or token missing Actions/Metadata read |
| Stage shows "Unknown" | job/step renamed; update `dashboard/stages.py` |
| 502 from Nginx | app container unhealthy: `docker compose logs app` |

## 11. Daily workflow

Edit in VS Code, `pytest`, `git commit`, `git push`. Watch GitHub Actions or the dashboard. If a stage fails, the dashboard shows which one, with the actual error and tips; the previous version keeps running.

## 12. Test checklist

- [ ] `pytest -v` passes locally; `docker compose up -d --build` starts three healthy containers.
- [ ] Add, edit, search and delete a student; restart (`docker compose restart app`) and `down` then `up`: data remains.
- [ ] Open a pull request: pipeline validates, tests and builds, but nothing is pushed or deployed.
- [ ] Push to `main` with all secrets: image `:<sha>` and `:latest` appear on Docker Hub; deployment succeeds; `/api/health` shows that SHA; dashboard shows all seven stages green.
- [ ] Remove the EC2 secrets: image still pushed, deploy shows grey/skipped with a warning.
- [ ] Break a test on purpose: pipeline fails at Tests, later stages are grey, dashboard names "Tests" with tips; production unchanged.
- [ ] Deploy a build that crashes at startup (e.g. raise an error in `create_app`): `deploy.sh` rolls back, the old version still answers, the run is marked failed.
- [ ] Run `./deploy/rollback.sh`, `./deploy/backup.sh` and `./deploy/restore.sh` on the server.
- [ ] Stop the student app (`docker stop student-app`): the dashboard stays reachable and shows health "Unreachable".
