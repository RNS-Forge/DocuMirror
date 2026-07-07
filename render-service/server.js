/**
 * server.js
 * ---------
 * Minimal Express microservice that renders an EJS template string
 * against a data object and returns the resulting HTML.
 *
 * Endpoint
 * --------
 *   POST /render
 *   Body (JSON):
 *     {
 *       "template": "<full EJS template string>",
 *       "data":     { ...extracted field values + layout object }
 *     }
 *   Response (200):
 *     { "html": "<rendered HTML string>" }
 *   Response (400 / 500):
 *     { "error": "<message>" }
 *
 *   GET /health
 *   Response (200): { "status": "ok" }
 */

"use strict";

const express = require("express");
const ejs = require("ejs");

const PORT = parseInt(process.env.RENDER_SERVICE_PORT || "4000", 10);
const LOG_LEVEL = (process.env.LOG_LEVEL || "INFO").toUpperCase();

const app = express();

// ── Middleware ──────────────────────────────────────────────────────────────
// Accept large payloads – EJS templates + base64 images can be sizeable
app.use(express.json({ limit: "10mb" }));

// ── Logging helper ──────────────────────────────────────────────────────────
function log(level, ...args) {
  const levels = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3 };
  if ((levels[level] ?? 1) >= (levels[LOG_LEVEL] ?? 1)) {
    const ts = new Date().toISOString();
    console.log(`${ts} [${level}] render-service:`, ...args);
  }
}

// ── Health check ────────────────────────────────────────────────────────────
app.get("/health", (_req, res) => {
  res.json({ status: "ok" });
});

// ── Main render endpoint ─────────────────────────────────────────────────────
app.post("/render", (req, res) => {
  const { template, data } = req.body;

  // --- Validate request body ---
  if (typeof template !== "string" || template.trim().length === 0) {
    log("WARNING", "Request missing 'template' field");
    return res.status(400).json({ error: "'template' must be a non-empty string" });
  }
  if (!data || typeof data !== "object") {
    log("WARNING", "Request missing 'data' field");
    return res.status(400).json({ error: "'data' must be a JSON object" });
  }

  log("DEBUG", `Rendering template (${template.length} chars) with ${Object.keys(data).length} data keys`);

  // --- Ensure required array fields are always arrays (defensive) ---
  const safeData = Object.assign({}, data);
  const arrayFields = ["item_table", "item_breakdown"];
  for (const field of arrayFields) {
    if (!Array.isArray(safeData[field])) {
      safeData[field] = safeData[field] ? [safeData[field]] : [];
    }
  }

  // --- Ensure layout is always an object so EJS can safely access layout.* ---
  if (!safeData.layout || typeof safeData.layout !== "object") {
    safeData.layout = {};
  }
  // Apply sensible defaults so EJS expressions like `layout.font_family || 'Arial'`
  // work even when the LLM returned nothing
  safeData.layout = Object.assign(
    {
      font_family: "Arial, sans-serif",
      font_size_body: "10px",
      has_border: false,
      header_bg_color: null,
      table_border_style: "1px solid #000",
      bold_labels: true,
      two_column_layout: false,
      column_alignments: null,
    },
    safeData.layout
  );

  // --- Render ---
  try {
    const html = ejs.render(template, safeData, {
      // Disable file includes – we pass the full template string directly
      views: [],
      // Propagate EJS errors with useful line numbers
      compileDebug: true,
      // rmWhitespace keeps output clean without affecting layout
      rmWhitespace: false,
    });

    log("INFO", `Rendered OK  (output: ${html.length} chars)`);
    return res.json({ html });
  } catch (err) {
    log("ERROR", "EJS render error:", err.message);
    return res.status(500).json({
      error: `EJS render failed: ${err.message}`,
    });
  }
});

// ── 404 catch-all ────────────────────────────────────────────────────────────
app.use((_req, res) => {
  res.status(404).json({ error: "Not found. Available endpoints: POST /render, GET /health" });
});

// ── Start server ─────────────────────────────────────────────────────────────
app.listen(PORT, "127.0.0.1", () => {
  log("INFO", `Render service listening on http://127.0.0.1:${PORT}`);
});
