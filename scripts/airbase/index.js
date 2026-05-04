const express = require('express');
const path = require('path');
const app = express();
const PORT = process.env.PORT || 3000;

// Serve static files from public/ — produced by
// `python3 scripts/build_iran_monitor.py --airbase /opt/airbase-iran/public`.
app.use(express.static(path.join(__dirname, 'public')));

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'healthy' });
});

app.listen(PORT, () => {
  console.log(`Iran Monitor running on port ${PORT}`);
});
