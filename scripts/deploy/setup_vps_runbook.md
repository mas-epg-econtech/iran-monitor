# Iran Monitor — VPS Setup Runbook

One-time setup steps to deploy the daily refresh + auto-push to GitHub
Pages on the Hetzner VPS (`204.168.224.154`). Mirrors the existing
`/opt/asean-dashboard/` pattern.

---

## 0. Prerequisites

- SSH access to `root@204.168.224.154`
- Python 3.11 and git already installed on the VPS
- The Iran Monitor repo cloned somewhere accessible
- Your local `.env` (with `CEIC_*`, `ANTHROPIC_API_KEY`, Google Sheets creds)
- Your local `data/iran_monitor.db` (47 MB — to seed; saves the 30-min cold-start)

---

## 1. Clone the repo into `/opt/iran-monitor/`

On the VPS:

```bash
cd /opt
git clone git@github-mas:mas-epg-econtech/iran-monitor.git
# OR (if no SSH alias yet on VPS, use HTTPS first then switch later):
# git clone https://github.com/mas-epg-econtech/iran-monitor.git
cd iran-monitor
```

## 2. Set up the Python virtual environment

```bash
cd /opt/iran-monitor
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements-pipeline.txt
```

If `requirements-pipeline.txt` doesn't exist yet, install the known
deps directly (and add the file later):

```bash
pip install pandas requests anthropic ceic-api-client \
            google-api-python-client google-auth google-auth-oauthlib \
            statsmodels scikit-learn yfinance python-dotenv
```

## 3. Seed the database (skip the 30-min cold-start)

From your Mac:

```bash
scp "/Users/kevinlim/Documents/MAS/Projects/ESD/Iran Monitor/data/iran_monitor.db" \
    root@204.168.224.154:/opt/iran-monitor/data/iran_monitor.db
```

This skips the initial PortWatch backfill on first cron run.

## 4. Copy credentials

```bash
# From your Mac:
scp "/Users/kevinlim/Documents/MAS/Projects/ESD/Iran Monitor/.env" \
    root@204.168.224.154:/opt/iran-monitor/.env
```

If you use a Google service-account JSON for the Bloomberg sheets
fetch, scp that too into `/opt/iran-monitor/` (path is referenced by
`update_data.py`'s `_get_sheets_service`).

On the VPS, append SMTP credentials for failure notifications. Suggest
Gmail + an app password (https://myaccount.google.com/apppasswords):

```bash
cat >> /opt/iran-monitor/.env << 'EOF'

# SMTP for failure notifications (deploy.sh → send_email.py)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=limkvn@gmail.com
SMTP_PASSWORD=<16-char Gmail app password>
ALERT_EMAIL_TO=limkvn@gmail.com
EOF
chmod 600 /opt/iran-monitor/.env
```

Test the email helper:

```bash
cd /opt/iran-monitor
set -a; source .env; set +a
python3.11 scripts/deploy/send_email.py \
    --subject "Iran Monitor — VPS setup test" \
    --body "If you see this, SMTP is wired up correctly."
```

You should see "sent to ..." and an email arrives.

## 5. Configure git for the bot identity

```bash
cd /opt/iran-monitor
git config user.name  "iran-monitor-bot"
git config user.email "noreply@iran-monitor.local"
```

## 6. Set up SSH deploy key (so the cron can `git push`)

```bash
# On the VPS:
ssh-keygen -t ed25519 -f /root/.ssh/id_ed25519_iran_monitor -C "iran-monitor-vps-deploy" -N ""
cat /root/.ssh/id_ed25519_iran_monitor.pub
# → copy the public key
```

Then in GitHub:
- Go to https://github.com/mas-epg-econtech/iran-monitor/settings/keys
- "Add deploy key"
- Title: `iran-monitor-vps-bot`
- Paste the public key
- **Tick "Allow write access"** (required for git push)

Add an SSH config entry on the VPS so this key resolves to a host alias:

```bash
cat >> /root/.ssh/config << 'EOF'

Host github-iran-monitor
    HostName github.com
    User git
    IdentityFile /root/.ssh/id_ed25519_iran_monitor
    IdentitiesOnly yes
EOF
```

Re-point the repo's origin remote to use this alias:

```bash
cd /opt/iran-monitor
git remote set-url origin git@github-iran-monitor:mas-epg-econtech/iran-monitor.git
```

Test:

```bash
ssh -T git@github-iran-monitor
# Should print: "Hi mas-epg-econtech/iran-monitor! You've successfully authenticated..."
git fetch origin && echo "fetch OK"
```

## 7. Make deploy.sh executable

```bash
chmod +x /opt/iran-monitor/scripts/deploy/deploy.sh
chmod +x /opt/iran-monitor/scripts/deploy/send_email.py
```

## 8. Smoke test — manual run

Run the deploy script once by hand to confirm the full flow works:

```bash
/opt/iran-monitor/scripts/deploy/deploy.sh 2>&1 | tee /tmp/iran-monitor-first-run.log
```

Expected: pipeline runs (probably ~5–10 min — most data sources are
incremental since the DB is seeded), HTML files get rebuilt, and either:
- "No HTML changes — skipping commit" (if absolutely nothing moved), or
- A commit + push with "Auto-refresh YYYY-MM-DDTHH:MMZ"

If it fails: read the log, fix, re-run.

## 9. Install the cron entry

```bash
crontab -e
```

Add this line:

```cron
30 22 * * * /opt/iran-monitor/scripts/deploy/deploy.sh >> /var/log/iran-monitor.log 2>&1
```

That fires daily at 22:30 UTC (06:30 SGT next day). Save and exit.

Verify:

```bash
crontab -l | grep iran-monitor
```

## 10. Permissions on the log file

```bash
sudo touch /var/log/iran-monitor.log
sudo chmod 644 /var/log/iran-monitor.log
sudo chown root:root /var/log/iran-monitor.log
```

## 11. Wait for the first scheduled run

It'll trigger at 22:30 UTC tonight. After it runs:

```bash
tail -200 /var/log/iran-monitor.log
git -C /opt/iran-monitor log --oneline -3
```

Confirm the latest commit is "Auto-refresh ..." with today's date and
that GitHub Pages picked up the deploy
(https://mas-epg-econtech.github.io/iran-monitor/).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "ssh: Could not resolve hostname github-iran-monitor" | SSH config alias missing on VPS | Re-do step 6's SSH config block |
| "Permission denied (publickey)" on push | Deploy key not registered or write access not ticked | Re-do step 6's GitHub-side registration; check "Allow write access" |
| Email helper "missing env vars" | SMTP_* not in .env | Re-do step 4's SMTP block |
| Email helper "SMTP send failed: 535" | Gmail app password wrong/revoked | Generate a new app password and update .env |
| Pipeline "ANTHROPIC_API_KEY not set" | .env not sourced by deploy.sh | Confirm .env exists at /opt/iran-monitor/.env and chmod 600 |
| Pipeline "CEIC credentials not set" | Same | Same — check .env |
| Cron doesn't fire | crontab entry wrong | `crontab -l` to inspect; check `/var/log/syslog | grep CRON` |
| Cron fires but no log appears | Log redirection wrong in cron line | Verify the `>> /var/log/iran-monitor.log 2>&1` is there |

## Updating the deployed code

When you push new commits to `main` from your Mac, the VPS will see them
on the next git pull (which deploy.sh doesn't currently do — it only
adds + commits + pushes). To pick up code changes on the VPS:

```bash
cd /opt/iran-monitor
git pull --rebase origin main   # picks up Mac-side commits
```

Future enhancement: add `git pull --rebase origin main` to the top of
deploy.sh so the VPS auto-syncs code changes too. Current behavior is
"VPS does data refresh, never code refresh" — a deliberate split so a
buggy code push doesn't auto-cascade onto the VPS until you've sanity
checked it.
