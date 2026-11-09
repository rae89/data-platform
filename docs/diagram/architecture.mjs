// Renders ../architecture.svg (embedded in README.md). Run `just diagram` after editing.
import { writeFileSync } from "node:fs";
import * as d3 from "d3";
import { JSDOM } from "jsdom";

const W = 1130, H = 540, NW = 170, NH = 56;
const color = { dagster: "#4f46e5", storage: "#b45309", obs: "#0f766e", portal: "#475569", bi: "#0369a1" };

const nodes = [
  { id: "schedule", x: 40, y: 140, kind: "dagster", title: "Schedules", sub: "ingest_sources daily" },
  { id: "ingest", x: 250, y: 140, kind: "dagster", title: "Ingest (dlt)", sub: "sources/<name>/*" },
  { id: "dbt", x: 250, y: 250, kind: "dagster", title: "dbt models + tests", sub: "staging → marts, checks" },
  { id: "sensors", x: 250, y: 360, kind: "dagster", title: "SLI sensors", sub: "dagster-victoria-sli" },
  { id: "logs", x: 250, y: 450, kind: "dagster", title: "VictoriaLogs handler", sub: "ships run logs" },
  { id: "duckdb", x: 490, y: 195, kind: "storage", title: "DuckDB", sub: "data/warehouse.duckdb" },
  { id: "vm", x: 490, y: 360, kind: "obs", title: "VictoriaMetrics", sub: ":8428" },
  { id: "vl", x: 490, y: 450, kind: "obs", title: "VictoriaLogs", sub: ":9428" },
  { id: "vmalert", x: 710, y: 270, kind: "obs", title: "vmalert", sub: "sli:* rules, SLO alerts" },
  { id: "grafana", x: 710, y: 405, kind: "obs", title: "Grafana", sub: ":3001 dashboards" },
  { id: "apis", x: 250, y: 8, kind: "portal", title: "Source APIs", sub: "IMF PortWatch (ArcGIS)" },
  { id: "dltdash", x: 710, y: 40, kind: "portal", title: "dlt dashboard", sub: ":2718 on demand, read-only" },
  { id: "bi", x: 710, y: 140, kind: "storage", title: "BI snapshot", sub: "data/bi.duckdb (read-only)" },
  { id: "superset", x: 930, y: 140, kind: "bi", title: "Superset", sub: ":8088 dashboards, SQL Lab" },
  { id: "github", x: 930, y: 250, kind: "portal", title: "GitHub", sub: "merged PRs, releases" },
  { id: "portal", x: 930, y: 350, kind: "portal", title: "Portal (Homepage)", sub: ":3002 links, health checks" },
];
const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));

// side: "h" connects right edge → left edge, "v" connects bottom → top.
const edges = [
  { from: "duckdb", to: "dltdash", label: "inspects" },  // early, so later labels draw over it
  { from: "vm", to: "portal", label: "live SLIs" },  // first, so other labels draw over its line
  { from: "github", to: "portal", side: "v", label: "feeds" },
  { from: "apis", to: "ingest", side: "v", label: "dlt" },
  { from: "duckdb", to: "bi", label: "copy" },
  { from: "bi", to: "superset", label: "reads" },
  { from: "schedule", to: "ingest", label: "runs" },
  { from: "ingest", to: "dbt", side: "v", label: "upstream of" },
  { from: "ingest", to: "duckdb", label: "loads" },
  { from: "dbt", to: "duckdb", label: "builds models" },
  { from: "sensors", to: "vm", label: "pushes SLIs" },
  { from: "logs", to: "vl", label: "run logs" },
  { from: "vm", to: "vmalert", label: "queries / writes sli:*" },
  { from: "vm", to: "grafana" },
  { from: "vl", to: "grafana" },
];

const { document } = new JSDOM("<body></body>").window;
const svg = d3.select(document.body).append("svg")
  .attr("xmlns", "http://www.w3.org/2000/svg")
  .attr("viewBox", `0 0 ${W} ${H}`).attr("width", W).attr("height", H)
  .attr("font-family", "-apple-system, Segoe UI, Helvetica, Arial, sans-serif");

svg.append("rect").attr("width", W).attr("height", H).attr("fill", "#ffffff");
svg.append("defs").append("marker")
  .attr("id", "arrow").attr("viewBox", "0 0 10 10").attr("refX", 9).attr("refY", 5)
  .attr("markerWidth", 7).attr("markerHeight", 7).attr("orient", "auto")
  .append("path").attr("d", "M0,0L10,5L0,10z").attr("fill", "#64748b");

// Dagster code location boundary.
svg.append("rect").attr("x", 20).attr("y", 90).attr("width", 430).attr("height", 435)
  .attr("rx", 12).attr("fill", "#eef2ff").attr("stroke", color.dagster).attr("stroke-dasharray", "6 4");
svg.append("text").attr("x", 36).attr("y", 114).attr("font-size", 14).attr("font-weight", 600)
  .attr("fill", color.dagster).text("Dagster · code location data_platform");

const link = d3.linkHorizontal();
const linkV = d3.linkVertical();
const g = svg.append("g");
for (const e of edges) {
  const a = byId[e.from], b = byId[e.to];
  const [path, mid] = e.side === "v"
    ? [linkV({ source: [a.x + NW / 2, a.y + NH], target: [b.x + NW / 2, b.y] }), [a.x + NW / 2 + 8, (a.y + NH + b.y) / 2 + 4]]
    : [link({ source: [a.x + NW, a.y + NH / 2], target: [b.x, b.y + NH / 2] }),
       [(a.x + NW + b.x) / 2, (a.y + b.y + NH) / 2 - 6]];
  g.append("path").attr("d", path).attr("fill", "none").attr("stroke", "#64748b")
    .attr("stroke-width", 1.5).attr("marker-end", "url(#arrow)");
  if (e.label) {
    g.append("text").attr("x", mid[0]).attr("y", mid[1]).attr("font-size", 11).attr("fill", "#475569")
      .attr("text-anchor", e.side === "v" ? "start" : "middle")
      .attr("paint-order", "stroke").attr("stroke", "#ffffff").attr("stroke-width", 4).text(e.label);
  }
}

const n = svg.append("g").selectAll("g").data(nodes).join("g")
  .attr("transform", (d) => `translate(${d.x},${d.y})`);
n.append("rect").attr("width", NW).attr("height", NH).attr("rx", 8)
  .attr("fill", "#ffffff").attr("stroke", (d) => color[d.kind]).attr("stroke-width", 2);
n.append("text").attr("x", NW / 2).attr("y", 24).attr("text-anchor", "middle")
  .attr("font-size", 14).attr("font-weight", 600).attr("fill", "#0f172a").text((d) => d.title);
n.append("text").attr("x", NW / 2).attr("y", 42).attr("text-anchor", "middle")
  .attr("font-size", 11).attr("fill", "#475569").text((d) => d.sub);

const out = new URL("../architecture.svg", import.meta.url);
writeFileSync(out, document.body.innerHTML + "\n");
console.log(`wrote ${out.pathname}`);
