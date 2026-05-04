#!/bin/bash
# Iran Monitor — VPS-side daily refresh & GitHub Pages auto-push.
#
# Invoked by cron on the VPS (see scripts/deploy/setup_vps_runbook.md for
# install steps). Runs the full data pipeline, then commits + pushes any
# changed HTML files so GitHub Pages picks them up.
#
# Failures (pipeline exit non-zero, push exit non-zero) trigger an email
# notification via scripts/deploy/send_email.py — requires SMTP env vars
# in /opt/iran-monitor/.env (SMTP_HOST/PORT/USER/PASSWORD + ALERT_EMAIL_TO).
#
# Usage from cron:
#   30 22 * * * /opt/iran-monitor/scripts/deploy/deploy.sh \
#                  >> /var/log/iran-monitor.log 2>&1

set -u
set -o pipefail

PROJECT_ROOT=/opt/iran-monitor
LOG_TS=$(date -u +%Y-%m-%dT%H:%MZ)

cd "$PROJECT_ROOT"

# Source .env so SMTP_* + everything-else credentials are in env for the
# pipeline + the email helper.
if [[ -f .env ]]; then
    set -a
    source .env
    set +a
fi

# Activate venv so python3.11 + pip-installed deps resolve.
# shellcheck disable=SC1091
source venv/bin/activate

echo
echo "=================================================================="
echo "[$LOG_TS] Iran Monitor cron refresh starting"
echo "=================================================================="

send_failure_email() {
    local subject=$1
    local body=$2
    if [[ -x "$PROJECT_ROOT/scripts/deploy/send_email.py" ]]; then
        python3.11 "$PROJECT_ROOT/scripts/deploy/send_email.py" \
            --subject "$subject" --body "$body" \
            || echo "[$LOG_TS] email helper itself failed (continuing)"
    fi
}

# 1. Run the pipeline. Capture combined output so we can build a
# meaningful commit message later.
PIPELINE_LOG=$(mktemp -t iran-pipeline.XXXXXX)
if ! python3.11 scripts/energy/update_data.py 2>&1 | tee "$PIPELINE_LOG"; then
    EXIT_CODE=${PIPESTATUS[0]}
    echo "[$LOG_TS] PIPELINE FAILED (exit $EXIT_CODE)"
    send_failure_email \
        "Iran Monitor cron FAILED at $LOG_TS" \
        "Pipeline exited $EXIT_CODE. Tail of log:
$(tail -50 "$PIPELINE_LOG")"
    rm -f "$PIPELINE_LOG"
    exit "$EXIT_CODE"
fi

# 2. Check if any HTML files changed. If not, skip commit/push entirely
# (the user asked for clean history with no no-op commits).
if git diff --quiet HEAD -- '*.html'; then
    echo "[$LOG_TS] No HTML changes — skipping commit"
    rm -f "$PIPELINE_LOG"
    exit 0
fi

# 3. Build a commit message from the pipeline log. Format chosen earlier:
#   Auto-refresh YYYY-MM-DDTHH:MMZ
#   Steps run: 1-12 (narratives: refreshed/skipped, shipping: refreshed/skipped)
#   Triggers fired: ... OR none
NARR_STATE="unknown"
if grep -qE '\[11/12\] Generating AI narratives — SKIPPED' "$PIPELINE_LOG"; then
    NARR_STATE="skipped"
elif grep -qE '\[11/12\] Generating AI narratives \(' "$PIPELINE_LOG"; then
    NARR_STATE="refreshed"
fi

SHIP_STATE="unknown"
if grep -qE '\[8/12\] Shipping nowcast — SKIPPED' "$PIPELINE_LOG"; then
    SHIP_STATE="skipped"
elif grep -qE '\[8/12\] Computing shipping nowcast' "$PIPELINE_LOG"; then
    SHIP_STATE="refreshed"
fi

# Trigger reasons — captured from the [10b/12] block. Limit to first ~5
# reasons to keep the commit message tidy.
TRIGGER_REASONS=$(grep -A 20 '\[10b/12\] Evaluating narrative triggers' "$PIPELINE_LOG" \
    | grep -E '^\s+-\s' | head -5 | sed 's/^\s\+-\s\+/  - /')
if [[ -z "$TRIGGER_REASONS" ]]; then
    TRIGGER_REASONS="  (no triggers section in log)"
fi

git add -A '*.html'

COMMIT_MSG="Auto-refresh $LOG_TS

Steps run: 1-12 (narratives: $NARR_STATE, shipping: $SHIP_STATE)
Trigger evaluation:
$TRIGGER_REASONS"

git commit -m "$COMMIT_MSG" || {
    EXIT_CODE=$?
    echo "[$LOG_TS] git commit failed (exit $EXIT_CODE)"
    send_failure_email \
        "Iran Monitor cron COMMIT FAILED at $LOG_TS" \
        "Pipeline succeeded but git commit failed (exit $EXIT_CODE)."
    rm -f "$PIPELINE_LOG"
    exit "$EXIT_CODE"
}

# 4. Push to origin/main. GitHub Pages auto-deploys from main.
if ! git push origin main; then
    EXIT_CODE=$?
    echo "[$LOG_TS] git push FAILED (exit $EXIT_CODE)"
    send_failure_email \
        "Iran Monitor cron PUSH FAILED at $LOG_TS" \
        "Pipeline succeeded and commit landed locally but git push failed
(exit $EXIT_CODE). Manually 'git push' from /opt/iran-monitor when fixed."
    rm -f "$PIPELINE_LOG"
    exit "$EXIT_CODE"
fi

rm -f "$PIPELINE_LOG"
echo "[$LOG_TS] Auto-refresh complete; pushed to origin/main"
