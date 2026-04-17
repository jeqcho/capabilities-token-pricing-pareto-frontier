// Loads outputs/models.json and renders three ECI × price plots.

const DATA_URL = "./models.json";
const PALETTE = [
  "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
  "#9467bd", "#8c564b", "#e377c2", "#17becf",
  "#bcbd22", "#7f7f7f", "#393b79", "#637939",
  "#8c6d31", "#843c39", "#7b4173",
];

// Ordered so the first match wins (e.g. "gpt-oss" before "gpt").
const FAMILY_PATTERNS = [
  [/^gpt-oss/i, "gpt-oss"],
  [/^gpt[- ]?5/i, "GPT-5"],
  [/^gpt[- ]?4/i, "GPT-4"],
  [/^gpt[- ]?3/i, "GPT-3"],
  [/^o[1-9](\b|-)/i, "OpenAI o-series"],
  [/^claude/i, "Claude"],
  [/^gemini/i, "Gemini"],
  [/^gemma/i, "Gemma"],
  [/^llama/i, "Llama"],
  [/^qwen/i, "Qwen"],
  [/^deepseek/i, "DeepSeek"],
  [/^mistral/i, "Mistral"],
  [/^mixtral/i, "Mistral"],
  [/^magistral/i, "Mistral"],
  [/^grok/i, "Grok"],
  [/^phi/i, "Phi"],
  [/^nemotron/i, "Nemotron"],
  [/^command/i, "Command"],
  [/^minimax/i, "MiniMax"],
  [/^muse/i, "Muse"],
  [/^yi[- ]/i, "Yi"],
  [/^kimi/i, "Kimi"],
  [/^glm/i, "GLM"],
];

const PLOTS = [
  { div: "plot-blended", priceKey: "price_blended", frontierKey: "on_frontier_blended",
    title: "ECI vs price (3:1 blended)", xLabel: "Price per 1M tokens, USD (3:1 input:output blend)" },
  { div: "plot-input", priceKey: "price_input", frontierKey: "on_frontier_input",
    title: "ECI vs input price", xLabel: "Input price per 1M tokens, USD" },
  { div: "plot-output", priceKey: "price_output", frontierKey: "on_frontier_output",
    title: "ECI vs output price", xLabel: "Output price per 1M tokens, USD" },
];

let allModels = [];
let familyColor = new Map();

function modelFamily(m) {
  const name = m.name || "";
  for (const [pattern, label] of FAMILY_PATTERNS) {
    if (pattern.test(name)) return label;
  }
  return m.org || "other";
}

function buildFamilyColorMap(models) {
  // Sort families by total member count descending so the largest groups get
  // the most distinctive colors.
  const counts = new Map();
  models.forEach(m => {
    const f = modelFamily(m);
    counts.set(f, (counts.get(f) || 0) + 1);
  });
  const sorted = [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([f]) => f);
  const map = new Map();
  sorted.forEach((f, i) => map.set(f, PALETTE[i % PALETTE.length]));
  return map;
}

function paretoStepped(frontierModels, priceKey) {
  const sorted = [...frontierModels].sort((a, b) => a[priceKey] - b[priceKey]);
  const xs = [];
  const ys = [];
  sorted.forEach((m, i) => {
    if (i > 0) {
      xs.push(m[priceKey]);
      ys.push(sorted[i - 1].eci);
    }
    xs.push(m[priceKey]);
    ys.push(m.eci);
  });
  return { xs, ys };
}

// Match "Claude Opus 4", "Claude Sonnet 4.6", "Claude Haiku 4.5" — version ≥ 4.
const CLAUDE_MODERN = /claude\s+\w+\s+(?:[4-9]|\d{2,})/i;

function familyFrontierSet(models, family, priceKey) {
  const group = models
    .filter(m => modelFamily(m) === family && m[priceKey] > 0 && m.eci != null)
    .filter(m => family !== "Claude" || CLAUDE_MODERN.test(m.name))
    .sort((a, b) => a[priceKey] - b[priceKey] || b.eci - a.eci);
  const frontier = new Set();
  let bestEci = -Infinity;
  for (const m of group) {
    if (m.eci > bestEci) {
      frontier.add(m.name);
      bestEci = m.eci;
    }
  }
  return frontier;
}

function buildTraces(models, cfg) {
  const visible = models.filter(m =>
    m[cfg.priceKey] != null && m.eci != null && m[cfg.priceKey] > 0
  );
  const claudeFrontier = familyFrontierSet(visible, "Claude", cfg.priceKey);
  // Order families by legend-friendly order: our palette-assigned order.
  const familiesInView = [...new Set(visible.map(modelFamily))]
    .sort((a, b) => {
      const ai = familyColor.has(a) ? [...familyColor.keys()].indexOf(a) : 999;
      const bi = familyColor.has(b) ? [...familyColor.keys()].indexOf(b) : 999;
      return ai - bi;
    });

  const LABELED_FAMILY = "Claude";

  const traces = [];
  familiesInView.forEach(family => {
    const group = visible.filter(m => modelFamily(m) === family);
    const color = familyColor.get(family) || "#888";
    const labelThis = family === LABELED_FAMILY;
    const hasFrontier = group.some(m => m[cfg.frontierKey]);

    // non-frontier (faded). Show in legend only if no frontier trace will carry
    // this family (otherwise the family would be absent from the legend entirely).
    const nonFrontier = group.filter(m => !m[cfg.frontierKey]);
    if (nonFrontier.length) {
      traces.push({
        type: "scatter",
        mode: labelThis ? "markers+text" : "markers",
        name: family,
        legendgroup: family,
        showlegend: !hasFrontier,
        x: nonFrontier.map(m => m[cfg.priceKey]),
        y: nonFrontier.map(m => m.eci),
        text: nonFrontier.map(m => labelThis && claudeFrontier.has(m.name) ? m.name : ""),
        hovertext: nonFrontier.map(tooltipText.bind(null, cfg)),
        hoverinfo: "text",
        textposition: "top right",
        textfont: { size: 10, color },
        marker: {
          color,
          opacity: 0.35,
          size: 8,
          symbol: nonFrontier.map(m => m.reasoning ? "circle-open" : "circle"),
          line: { color, width: 1.5 },
        },
      });
    }

    // frontier (solid)
    const frontier = group.filter(m => m[cfg.frontierKey]);
    if (frontier.length) {
      traces.push({
        type: "scatter",
        mode: labelThis ? "markers+text" : "markers",
        name: family,
        legendgroup: family,
        x: frontier.map(m => m[cfg.priceKey]),
        y: frontier.map(m => m.eci),
        text: frontier.map(m => labelThis && claudeFrontier.has(m.name) ? m.name : ""),
        hovertext: frontier.map(tooltipText.bind(null, cfg)),
        hoverinfo: "text",
        textposition: "top right",
        textfont: { size: 10, color },
        marker: {
          color,
          opacity: 1,
          size: 11,
          symbol: frontier.map(m => m.reasoning ? "circle-open" : "circle"),
          line: { color: "#111", width: 1.5 },
        },
      });
    }
  });

  // Pareto stepped line (single trace over all frontier points)
  const allFrontier = visible.filter(m => m[cfg.frontierKey]);
  if (allFrontier.length > 1) {
    const { xs, ys } = paretoStepped(allFrontier, cfg.priceKey);
    traces.push({
      type: "scatter", mode: "lines",
      name: "Pareto frontier",
      x: xs, y: ys,
      line: { color: "#111", width: 2, dash: "solid" },
      hoverinfo: "skip",
    });
  }

  return traces;
}

function tooltipText(cfg, m) {
  const price = m[cfg.priceKey];
  const priceStr = price != null ? `$${price.toFixed(3)}/M` : "—";
  const parts = [
    `<b>${m.name}</b>`,
    m.org ? m.org : null,
    m.release_date ? `released ${String(m.release_date).slice(0, 10)}` : null,
    `ECI: ${m.eci?.toFixed?.(1) ?? m.eci}`,
    `price: ${priceStr}`,
    m.reasoning ? "<i>reasoning model</i>" : null,
  ].filter(Boolean);
  return parts.join("<br>");
}

function render() {
  const hideReasoning = document.getElementById("hide-reasoning").checked;
  const filtered = hideReasoning
    ? allModels.filter(m => !m.reasoning)
    : allModels;

  PLOTS.forEach(cfg => {
    const traces = buildTraces(filtered, cfg);
    const layout = {
      title: { text: cfg.title, font: { size: 16 } },
      xaxis: {
        title: cfg.xLabel,
        type: "log",
        gridcolor: "#eee",
        zeroline: false,
      },
      yaxis: {
        title: "ECI",
        gridcolor: "#eee",
        zeroline: false,
      },
      hovermode: "closest",
      margin: { l: 60, r: 20, t: 50, b: 60 },
      legend: { orientation: "h", y: -0.2 },
      paper_bgcolor: "white",
      plot_bgcolor: "white",
    };
    Plotly.react(cfg.div, traces, layout, {
      displaylogo: false,
      responsive: true,
    });
  });
}

async function main() {
  const status = document.getElementById("status");
  try {
    status.textContent = "loading…";
    const resp = await fetch(DATA_URL, { cache: "no-store" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    allModels = data.models || [];
    familyColor = buildFamilyColorMap(allModels);

    const genAt = data.generated_at ? new Date(data.generated_at).toUTCString() : "unknown";
    document.getElementById("generated-at").textContent = `Data generated ${genAt}. ${data.model_count ?? allModels.length} models plotted; ${data.missing_pricing_count ?? 0} awaiting pricing.`;
    status.textContent = `${allModels.length} models`;

    render();
    document.getElementById("hide-reasoning").addEventListener("change", render);
  } catch (err) {
    status.textContent = `failed to load data: ${err.message}`;
    console.error(err);
  }
}

main();
