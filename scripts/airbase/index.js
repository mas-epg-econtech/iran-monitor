// Iran Monitor — Airbase Express server.
// Tiny static-file server. Airbase enforces CSP at the edge so we don't
// need any per-route CSP headers here; just hand out the files in public/.

const express = require('express');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// Static files. The CSP-compliant build output lives in public/ —
// produced by `python3 scripts/build_iran_monitor.py --airbase /opt/airbase-iran/public`.
app.use(express.static(path.join(__dirname, 'public'), {
  // Cache HTML briefly so a fresh deploy is picked up quickly; cache
  // versioned vendor JS for longer (rebuilds replace the whole public/
  // dir so cache busting at the deploy boundary is fine).
  setHeaders: (res, filePath) => {
    if (filePath.endsWith('.html')) {
      res.setHeader('Cache-Control', 'public, max-age=300');     // 5 min
    } else if (filePath.includes('/vendor/')) {
      res.setHeader('Cache-Control', 'public, max-age=86400');   // 1 day
    }
  },
}));

// Health check for Airbase / monitoring.
app.get('/health', (_req, res) => {
  res.json({ status: 'ok', service: 'iran-monitor' });
});

app.listen(PORT, () => {
  console.log(`Iran Monitor server listening on port ${PORT}`);
});
