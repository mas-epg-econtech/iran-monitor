# Iran Monitor — Airbase Setup Runbook

One-time steps to scaffold the Airbase project at `/opt/airbase-iran/`
on the VPS. After these steps, `deploy.sh` will automatically include
the Airbase deploy on every cron run.

Mirrors `/opt/airbase-asean/` — copy-paste with the Airbase handle
changed to `econtech/iran-monitor`.

---

## 1. Create the Airbase project directory + copy templates

On the **VPS**:

```bash
mkdir -p /opt/airbase-iran/public
cd /opt/airbase-iran

cp /opt/iran-monitor/scripts/airbase/airbase.json    .
cp /opt/iran-monitor/scripts/airbase/Dockerfile      .
cp /opt/iran-monitor/scripts/airbase/index.js        .
cp /opt/iran-monitor/scripts/airbase/package.json    .

ls -la
```

You should see `airbase.json`, `Dockerfile`, `index.js`, `package.json`,
and an empty `public/` subdirectory.

Compare with the existing ASEAN project to spot any pattern differences:

```bash
diff -q /opt/airbase-iran/Dockerfile  /opt/airbase-asean/Dockerfile  || true
diff -q /opt/airbase-iran/index.js    /opt/airbase-asean/index.js    || true
diff -q /opt/airbase-iran/package.json /opt/airbase-asean/package.json || true
```

If the ASEAN version differs in important ways (different base image,
different routes, etc.), copy/adapt rather than diverge — the templates
in `/opt/iran-monitor/scripts/airbase/` are best-effort based on the
deploy-skill doc.

## 2. Add Airbase credentials to `.env`

Get your access keys from https://console.airbase.tech.gov.sg → Settings → Credentials.

On the VPS, append to `/opt/iran-monitor/.env`:

```bash
cat >> /opt/iran-monitor/.env << 'EOF'

# Airbase CI mode credentials (deploy.sh → airbase login --ci)
AIRBASE_ACCESS_KEY_ID=<your-key-id>
AIRBASE_SECRET_ACCESS_KEY=<your-secret>
EOF
```

(The secret values can also be reused from whatever ASEAN's `.env`
uses, if it's the same Airbase account.)

## 3. Verify `~/.airbaserc` exists

Per the airbase-deploy-skill notes, `airbase login --ci` requires
`~/.airbaserc` to already exist. It should already be there from the
ASEAN setup. Verify:

```bash
ls -la ~/.airbaserc
```

If it doesn't exist, on your **Mac** run `airbase login` interactively
(opens a browser), then scp the file:

```bash
scp ~/.airbaserc root@204.168.224.154:~/.airbaserc
```

## 4. First manual build + deploy

On the VPS:

```bash
cd /opt/iran-monitor
source venv/bin/activate
set -a; source .env; set +a

# Build the CSP-compliant variant into the airbase public/ dir
python3 scripts/build_iran_monitor.py --airbase /opt/airbase-iran/public

# Verify the contents
ls -la /opt/airbase-iran/public/
ls -la /opt/airbase-iran/public/vendor/

# Login + build + deploy
cd /opt/airbase-iran
airbase login --ci
airbase build
airbase deploy --yes
```

Expected: a stream of build / push / deploy output, ending in a "Deployed
to https://iran-monitor.app.tc1.airbase.sg" message (or similar — see
the skill doc for exact format).

## 5. Visit the live URL

Open `https://iran-monitor.app.tc1.airbase.sg` in your browser.

If it loads cleanly (charts render, tabs switch, status badges visible):
done. Future cron runs will redeploy automatically.

If you see a blank page or charts missing, open browser DevTools →
Console and look for CSP errors:

- `Refused to execute inline script ...` → an inline `<script>` slipped
  through the csp_transform. Run `grep '<script>' /opt/airbase-iran/public/*.html`
  to find it. Either fix `csp_transform.py` to handle the case or
  patch the offending HTML by hand.
- `Refused to load script from 'https://...'` → a CDN URL slipped
  through. Same approach: `grep 'https://' /opt/airbase-iran/public/*.html`.
- `Refused to execute event handler ...` → an `onclick`/`onchange`
  attribute slipped through. `grep -E 'on(click|change)=' /opt/airbase-iran/public/*.html`.

## 6. Cron picks it up automatically

`deploy.sh` already has the Airbase deploy step (Step 5) — it auto-
detects whether `/opt/airbase-iran/` exists. Tonight's 22:30 UTC cron
run will rebuild + redeploy without further action.

To verify after the next cron run:

```bash
tail -100 /var/log/iran-monitor.log | grep -i airbase
```

You should see "Airbase deploy complete" near the end of the log block.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `airbase: command not found` | CLI not installed on VPS | Check `/usr/local/bin/airbase`; reinstall per the deploy skill if missing |
| `airbase login --ci` crashes with nil pointer | `~/.airbaserc` missing | scp it from your Mac (step 3 above) |
| `airbase login --ci` says "not logged in" despite env vars | env vars not exported in current shell | `set -a; source .env; set +a` then retry |
| "Refused to execute inline script" in browser | csp_transform missed an inline `<script>` block | grep + patch + improve csp_transform.py |
| "Refused to load script from cdnjs..." | csp_transform missed a CDN reference | grep + add to `_CDN_VENDOR_MAP` in csp_transform.py |
| Charts blank but no console errors | dashboard.js loaded but didn't find CHART_CONFIGS | check `<script src="chart-configs-<page>.js">` is loaded BEFORE `dashboard.js` |
| 502/504 from Airbase | Container crashed | `airbase logs` — usually a typo in index.js or missing `node_modules` |
