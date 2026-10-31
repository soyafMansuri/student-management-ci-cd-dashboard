const $ = (id) => document.getElementById(id);
const LABELS = { success: "Success", failed: "Failed", in_progress: "In progress", pending: "Pending",
  skipped: "Skipped", cancelled: "Cancelled", unknown: "Unknown", healthy: "Healthy", unhealthy: "Unhealthy",
  unreachable: "Unreachable", not_configured: "Not configured" };
const refreshMs = (parseInt(document.body.dataset.refresh, 10) || 20) * 1000;
let data = null;

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}
function link(text, href) {
  const a = el("a", null, text);
  if (href && /^https:\/\//.test(href)) { a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer"; }
  return a;
}
const fmtTime = (iso) => (iso ? new Date(iso).toLocaleString() : "—");
function fmtDur(s) {
  if (s === null || s === undefined) return "—";
  const m = Math.floor(s / 60);
  return m ? `${m}m ${s % 60}s` : `${s}s`;
}
const label = (s) => LABELS[s] || "Not available";

function card(title, value, sub, extra) {
  const c = el("div", "card");
  c.append(el("span", "label", title), el("span", "value", value));
  if (sub) c.append(el("span", "sub", sub));
  if (extra) c.append(extra);
  return c;
}

function renderCards(d) {
  const box = $("cards");
  box.replaceChildren();
  const c = d.counts || {}, s = d.summary || {}, h = d.health || {};
  const num = (v) => (v === undefined ? "—" : v);
  box.append(
    card("Total pipeline runs", num(c.total)),
    card("Successful runs", num(c.success)),
    card("Failed runs", num(c.failed)),
    card("Running now", num(c.running)),
    card("Latest pipeline", s.latest_state ? label(s.latest_state) : "No runs", null,
         s.latest_run_url ? link("View on GitHub", s.latest_run_url) : null),
  );
  box.append(card("Latest Docker image tag",
    s.latest_image ? s.latest_image.tag.slice(0, 12) : "None published",
    s.latest_image ? "Commit SHA tag, published " + fmtTime(s.latest_image.published_at) : "No run has pushed an image yet"));
  box.append(card("Image build / push",
    `${label(s.latest_image_build)} / ${label(s.latest_image_push)}`, "From the latest pipeline run",
    d.dockerhub_url ? link(d.image_repo, d.dockerhub_url) : el("span", "sub", "IMAGE_REPO not configured")));
  box.append(card("Last deployment",
    s.last_deployment ? label(s.last_deployment.state) : "None yet",
    s.last_deployment ? fmtTime(s.last_deployment.at) : "No run has attempted a deployment",
    s.last_deployment ? link("View run", s.last_deployment.run_url) : null));
  box.append(card("Application health", label(h.state),
    h.state === "healthy" ? `${h.latency_ms} ms · checked ${fmtTime(h.checked_at)}` : (h.detail || `HTTP ${h.http_status || "—"}`)));
  box.append(card("Deployed image",
    d.deployed ? d.deployed.tag.slice(0, 12) : "Unknown",
    d.deployed ? d.deployed.source : "Only shown when the running app reports its version"));
  box.append(card("Last successful deployment",
    s.last_successful_deployment ? fmtTime(s.last_successful_deployment.at) : "None yet",
    s.last_successful_deployment ? "Deploy and health check both passed" : null));
}

function renderRun(r) {
  const box = el("article", "run " + r.state);
  const head = el("div", "run-head");
  const title = el("h3");
  title.append(`${r.name} `, link(`#${r.run_number} (run ${r.id})`, r.url));
  head.append(title, el("span", "badge " + r.state, label(r.state)));
  box.append(head, el("p", "msg", `${r.message || "(no commit message)"} — ${r.short_sha}`));
  box.append(el("div", "meta",
    `Branch: ${r.branch} · Trigger: ${r.event} · Started: ${fmtTime(r.started_at)} · Finished: ${fmtTime(r.completed_at)} · Duration: ${fmtDur(r.duration_seconds)} · GitHub status: ${r.status}/${r.conclusion || "—"}`));

  const pipe = el("div", "pipeline");
  for (const s of r.stages) {
    const st = el("div", "stage " + s.state);
    st.append(el("b", null, s.label), el("span", null, label(s.state)));
    pipe.append(st);
  }
  box.append(pipe);
  box.append(el("div", "results",
    `Docker build: ${label(r.docker_build)} · Docker Hub push: ${label(r.docker_push)} · AWS deploy: ${label(r.deploy)}` +
    (r.image_tag ? ` · Image tag: ${r.image_tag.slice(0, 12)}` : "")));

  if (r.failure) {
    const f = r.failure, fb = el("div", "failure");
    fb.append(el("h4", null, `Failed at: ${f.stage || "unidentified stage"}`));
    fb.append(el("div", null, `Job: ${f.job || "unknown"} · Step: ${f.step || "unknown"} · Status: ${f.status}/${f.conclusion}`));
    if (f.messages.length) {
      const ul = el("ul");
      f.messages.forEach((m) => { const li = el("li"); li.append(el("code", null, m)); ul.append(li); });
      fb.append(ul);
    }
    const tips = el("ul");
    f.suggestions.forEach((t) => tips.append(el("li", null, t)));
    fb.append(el("div", null, "What to try:"), tips, link("Open the full log on GitHub", f.url));
    box.append(fb);
  }
  return box;
}

function fillSelect(id, values) {
  const sel = $(id), current = sel.value;
  sel.replaceChildren(el("option", null, "All"));
  sel.firstChild.value = "";
  [...new Set(values)].filter(Boolean).sort().forEach((v) => { const o = el("option", null, v); o.value = v; sel.append(o); });
  sel.value = [...sel.options].some((o) => o.value === current) ? current : "";
}

function renderRuns() {
  const box = $("runs"), none = $("no-runs");
  box.replaceChildren();
  const fb = $("f-branch").value, fw = $("f-workflow").value, fs = $("f-status").value;
  const runs = (data.runs || []).filter((r) =>
    (!fb || r.branch === fb) && (!fw || r.name === fw) && (!fs || r.state === fs));
  none.hidden = runs.length > 0;
  if (!runs.length) none.textContent = data.runs && data.runs.length
    ? "No runs match these filters." : "No workflow runs are available yet. Push a commit to start the pipeline.";
  runs.forEach((r) => box.append(renderRun(r)));
}

function render(d) {
  data = d;
  $("repo-line").textContent = d.repo ? `Repository: ${d.repo}` : "Repository not configured";
  const banner = $("banner");
  banner.hidden = !d.error;
  banner.className = "banner" + (d.stale ? " warn" : "");
  banner.textContent = d.error ? (d.stale ? `${d.error} Showing the last data received.` : d.error) : "";
  renderCards(d);
  fillSelect("f-branch", (d.runs || []).map((r) => r.branch));
  fillSelect("f-workflow", (d.runs || []).map((r) => r.name));
  renderRuns();
}

async function load(force = false) {
  try {
    const res = await fetch("/api/dashboard" + (force ? "?force=1" : ""), { cache: "no-store" });
    if (res.status === 401) { location.reload(); return; }
    if (!res.ok) throw new Error(`Dashboard server returned HTTP ${res.status}`);
    render(await res.json());
    $("last-refresh").textContent = "Last refresh: " + new Date().toLocaleTimeString();
  } catch (e) {
    const b = $("banner");
    b.hidden = false; b.className = "banner warn";
    b.textContent = `Could not refresh: ${e.message}. Will retry automatically.`;
  }
}

["f-branch", "f-workflow", "f-status"].forEach((id) => $(id).addEventListener("change", () => data && renderRuns()));
$("refresh-btn").addEventListener("click", () => load(true));
load();
setInterval(load, refreshMs);
