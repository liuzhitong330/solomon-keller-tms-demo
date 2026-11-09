(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const NS = "http://www.w3.org/2000/svg";
  const accent = "#1f7a8c";
  const controls = {
    participant: $("participant-select"), channel: $("channel-select"),
    window: $("window-select"), budget: $("budget-select")
  };
  let data;
  let state = { participant:"S01", channel:"C3", window:"early", budget:50, minR:0.8, maxRms:20 };
  let reviewRows = [];

  function finite(value) { return typeof value === "number" && Number.isFinite(value); }
  function number(value, places = 2) { return finite(value) ? value.toFixed(places) : "not defined"; }
  function setText(id, text) { $(id).textContent = text; }
  function svg(tag, attrs = {}, text) {
    const node = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function textNode(parent, x, y, text, extra = {}) {
    parent.appendChild(svg("text", { x, y, fill:"#666", "font-size":12, ...extra }, text));
  }
  function median(values) {
    const ordered = values.filter(finite).sort((a,b) => a-b);
    if (!ordered.length) return null;
    const mid = Math.floor(ordered.length / 2);
    return ordered.length % 2 ? ordered[mid] : (ordered[mid-1] + ordered[mid]) / 2;
  }
  function selectedParticipant() { return data.participants.find((p) => p.id === state.participant); }
  function selectedReadout(p = selectedParticipant()) { return p.readouts[state.channel][state.window]; }
  function selectedBudget(p = selectedParticipant(), n = state.budget) {
    return selectedReadout(p).budgets.find((budget) => budget.n === n);
  }
  function windowLabel() {
    const window = data.meta.windows[state.window];
    return `${window.start_ms}–${window.end_ms} ms`;
  }
  function classify(budget) {
    if (!budget || !finite(budget.r.p10) || !finite(budget.rms_pct.median)) {
      return { pass:false, reason:"Undefined measurement" };
    }
    const reasons = [];
    if (budget.r.p10 < state.minR) reasons.push("Shape varies");
    if (budget.rms_pct.median > state.maxRms) reasons.push("Amplitude varies");
    return { pass:reasons.length === 0, reason:reasons.join("; ") || "Meets current rule" };
  }
  function option(select, value, label) {
    const node = document.createElement("option");
    node.value = value;
    node.textContent = label;
    select.appendChild(node);
  }
  function polyline(points, stroke, attrs = {}) {
    return svg("polyline", { points:points.map(([x,y]) => `${x},${y}`).join(" "), fill:"none", stroke,
      "stroke-width":2, "stroke-linejoin":"round", ...attrs });
  }
  function chartTitle(root, title, description) {
    root.replaceChildren(svg("title", {}, title), svg("desc", {}, description));
  }

  function renderWaveform() {
    const p = selectedParticipant();
    const readout = selectedReadout(p);
    const b = selectedBudget(p);
    const times = readout.time_ms;
    const first = b.example;
    setText("trial-budget-note", `${b.n} trials in set A + ${b.n} different trials in set B: ${2*b.n} distinct trials out of ${p.n_epochs} retained. The sets never overlap within a comparison.`);
    const mean = times.map((t) => {
      const index = data.meta.time_ms.findIndex((time) => Math.abs(time-t) < 0.00001);
      if (index < 0) throw new Error("A plotted latency is missing from the checked time axis.");
      return p.full_mean_uv[state.channel][index];
    });
    const root = $("hero-viz");
    chartTitle(root, `${p.id}, ${state.channel}, ${windowLabel()}, ${b.n} trials per set`,
      "Set A and set B contain disjoint retained trials. Gray dashed line is the full average for context. Voltage axis rescales for each selection.");
    const bounds = { left:56, top:26, width:525, height:224 };
    const maxAbs = Math.max(0.01, ...first.a_uv.map(Math.abs), ...first.b_uv.map(Math.abs), ...mean.map(Math.abs));
    const limit = maxAbs * 1.15;
    const x = (t) => bounds.left + (t-times[0]) / (times[times.length-1]-times[0]) * bounds.width;
    const y = (v) => bounds.top + (limit-v) / (2*limit) * bounds.height;
    [-1,-0.5,0,0.5,1].forEach((fraction) => {
      const value = fraction * limit;
      root.appendChild(svg("line", { x1:bounds.left, y1:y(value), x2:bounds.left+bounds.width, y2:y(value),
        stroke:fraction === 0 ? "#bbb" : "#e8e8e8" }));
      textNode(root, bounds.left-8, y(value)+4, number(value, limit < 1 ? 2 : 1), { "text-anchor":"end" });
    });
    for (let tick = 0; tick <= 4; tick += 1) {
      const time = times[0] + (times[times.length-1]-times[0]) * tick/4;
      textNode(root, x(time), bounds.top+bounds.height+22, number(time, 0), { "text-anchor":"middle" });
    }
    textNode(root, bounds.left, 14, "µV");
    textNode(root, bounds.left+bounds.width/2, 295, "Latency after pulse (ms)", { "text-anchor":"middle" });
    root.appendChild(polyline(times.map((t,i) => [x(t), y(mean[i])]), "#999", { "stroke-dasharray":"5 4", "stroke-width":1.7 }));
    root.appendChild(polyline(times.map((t,i) => [x(t), y(first.b_uv[i])]), "#333"));
    root.appendChild(polyline(times.map((t,i) => [x(t), y(first.a_uv[i])]), accent, { "stroke-width":2.5 }));

    setText("readout", `${p.id} · ${state.channel} · ${windowLabel()}. In this displayed split, shape agreement is r = ${number(first.r)} and RMS amplitude discrepancy is ${number(first.rms_pct,1)}%. The summaries below use all ${data.meta.iterations} seeded splits, not just these two lines. Voltage axes rescale between selections.`);
    setText("metric-one", number(b.r.median));
    setText("metric-two", finite(b.rms_pct.median) ? `${number(b.rms_pct.median,1)}%` : "not defined");
    setText("metric-three", String(p.n_epochs));
    setText("variability-note", `Across ${data.meta.iterations} splits: shape r 10th–90th percentile ${number(b.r.p10)} to ${number(b.r.p90)} (${b.r.n_valid} defined); RMS discrepancy ${number(b.rms_pct.p10,1)}–${number(b.rms_pct.p90,1)}% (${b.rms_pct.n_valid} defined). These are resampling ranges, not confidence intervals. Each comparison uses ${2*b.n} distinct trials.`);
  }

  function renderBudget() {
    const p = selectedParticipant();
    const budgets = data.meta.budgets;
    const points = budgets.map((n) => selectedBudget(p,n).r.p10);
    const cohort = budgets.map((n) => median(data.participants.map((subject) => selectedBudget(subject,n).r.p10)));
    const root = $("budget-viz");
    chartTitle(root, `Trial-budget sensitivity, ${p.id}, ${state.channel}, ${windowLabel()}`,
      "Teal shows selected participant lower-decile correlation. Gray shows the cohort median of participant lower-decile correlations. Dashed line is the editable review threshold. Select a point to change the active trial budget.");
    const bounds = { left:56, top:35, width:525, height:190 };
    const x = (n) => bounds.left+(n-budgets[0])/(budgets[budgets.length-1]-budgets[0])*bounds.width;
    const y = (r) => bounds.top+(1-r)/2*bounds.height;
    [-1,-0.5,0,0.5,1].forEach((r) => {
      root.appendChild(svg("line", {x1:bounds.left,y1:y(r),x2:bounds.left+bounds.width,y2:y(r),stroke:"#e8e8e8"}));
      textNode(root,bounds.left-8,y(r)+4,r.toFixed(1),{"text-anchor":"end"});
    });
    root.appendChild(svg("line", { x1:bounds.left,y1:y(state.minR),x2:bounds.left+bounds.width,y2:y(state.minR),stroke:"#aaa","stroke-dasharray":"3 5" }));
    if (cohort.every(finite)) root.appendChild(polyline(budgets.map((n,i) => [x(n),y(cohort[i])]), "#999", {"stroke-width":2}));
    // Missing values are shown as gaps, never silently coerced to zero.
    for (let i=1;i<budgets.length;i+=1) {
      if (finite(points[i-1]) && finite(points[i])) root.appendChild(polyline([[x(budgets[i-1]),y(points[i-1])],[x(budgets[i]),y(points[i])]],accent));
    }
    budgets.forEach((n,i) => {
      textNode(root,x(n),249,String(n),{"text-anchor":"middle"});
      if (!finite(points[i])) return;
      const group = svg("g", { role:"button", tabindex:0, "data-budget":n, "aria-label":`${n} trials per set; ${p.id} lower-decile r ${number(points[i])}`, "aria-pressed":String(n===state.budget) });
      group.appendChild(svg("circle", {cx:x(n),cy:y(points[i]),r:n===state.budget ? 6 : 4.5,fill:n===state.budget ? accent : "#fff",stroke:accent,"stroke-width":2}));
      group.appendChild(svg("title", {}, `${n} per set: ${number(points[i],3)}`));
      const choose = () => { state.budget=n; controls.budget.value=String(n); render(); };
      group.addEventListener("click",choose);
      group.addEventListener("keydown", (event) => { if (event.key==="Enter" || event.key===" ") {event.preventDefault();choose();$("budget-viz").querySelector(`[data-budget="${n}"]`).focus();} });
      root.appendChild(group);
    });
    textNode(root,bounds.left,17,"Lower-decile r");
    textNode(root,323,280,"Trials per set (two disjoint sets)",{"text-anchor":"middle"});
    setText("budget-note", `${p.id}: lower-decile r changes from ${number(points[0])} at ${budgets[0]} trials per set to ${number(points[points.length-1])} at ${budgets[budgets.length-1]}. Teal = selected participant; gray = cohort median; dotted = current shape threshold. Select a teal point or use the trial selector above. More trials need not improve every finite resampling estimate.`);
  }

  function renderCohort() {
    reviewRows = data.participants.map((participant) => {
      const b = selectedBudget(participant);
      return { participant, b, ...classify(b) };
    });
    const passed = reviewRows.filter((row) => row.pass).length;
    const selection = classify(selectedBudget());
    setText("cohort-readout", `${passed} of ${reviewRows.length} participants meet the current descriptive rule at ${state.channel}, ${windowLabel()}, ${state.budget} + ${state.budget} trials. ${state.participant}: ${selection.reason.toLowerCase()}. Remaining estimates are review candidates, not exclusions.`);
    setText("cohort-caption", `${state.channel} · ${windowLabel()} · ${state.budget} trials per set. RMS column is the median percentage discrepancy. Select a participant to inspect its waveforms.`);
    const body = $("cohort-body");
    body.replaceChildren();
    const filtered = reviewRows.filter((row) => !$("review-only").checked || !row.pass)
      .sort((a,b) => ((finite(a.b.r.p10) ? a.b.r.p10 : -2) - (finite(b.b.r.p10) ? b.b.r.p10 : -2)) || a.participant.id.localeCompare(b.participant.id));
    if (!filtered.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan=4;
      cell.textContent="No estimates need review under these settings. Uncheck the filter to inspect every participant.";
      row.appendChild(cell); body.appendChild(row);
    }
    filtered.forEach((entry) => {
      const row=document.createElement("tr");
      if (entry.participant.id===state.participant) row.setAttribute("aria-selected","true");
      const name=document.createElement("td");
      const button=document.createElement("button");
      button.type="button"; button.textContent=entry.participant.id;
      button.setAttribute("aria-label",`Inspect ${entry.participant.id} waveform`);
      button.addEventListener("click",() => {
        state.participant=entry.participant.id; controls.participant.value=state.participant; render();
        $("a1").scrollIntoView({behavior:window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"});
        controls.participant.focus({preventScroll:true});
      });
      name.appendChild(button); row.appendChild(name);
      [number(entry.b.r.p10,3), finite(entry.b.rms_pct.median) ? `${number(entry.b.rms_pct.median,1)}%` : "not defined", entry.reason].forEach((value) => {
        const cell=document.createElement("td"); cell.textContent=value; row.appendChild(cell);
      });
      body.appendChild(row);
    });
  }

  function exportCSV() {
    const columns=["participant","electrode","window_start_ms","window_end_ms","trials_per_set","retained_trials","r_p10","r_median","r_p90","rms_pct_p10","rms_pct_median","rms_pct_p90","r_defined_splits","rms_defined_splits","minimum_r_p10","maximum_rms_median_pct","meets_descriptive_rule","review_reason"];
    const w=data.meta.windows[state.window];
    const rows=reviewRows.map(({participant,b,pass,reason}) => [participant.id,state.channel,w.start_ms,w.end_ms,state.budget,participant.n_epochs,b.r.p10,b.r.median,b.r.p90,b.rms_pct.p10,b.rms_pct.median,b.rms_pct.p90,b.r.n_valid,b.rms_pct.n_valid,state.minR,state.maxRms,pass,reason]);
    const escape=(value) => value===null || value===undefined ? "" : `"${String(value).replace(/"/g,'""')}"`;
    const content=[columns,...rows].map((row) => row.map(escape).join(",")).join("\r\n")+"\r\n";
    const url=URL.createObjectURL(new Blob([content],{type:"text/csv;charset=utf-8"}));
    const anchor=document.createElement("a"); anchor.href=url;
    anchor.download=`tms-review-${state.channel}-${state.window}-n${state.budget}.csv`;
    document.body.appendChild(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url),1000);
  }

  function render() { renderWaveform(); renderBudget(); renderCohort(); }
  function thresholdChange() {
    const r=$("correlation-threshold"), rms=$("rms-threshold");
    if (!r.checkValidity() || !rms.checkValidity() || r.value==="" || rms.value==="") {
      setText("threshold-status", "Rule unchanged. Enter r from −1 to 1 in 0.05 steps and RMS discrepancy from 0 to 200% in 5-point steps.");
      return;
    }
    setText("threshold-status", "");
    state.minR=Number(r.value); state.maxRms=Number(rms.value);
    renderBudget(); renderCohort();
  }
  function initialize(results) {
    if (!results || !results.meta || !Array.isArray(results.participants) || results.participants.length!==22) throw new Error("The complete checked 22-participant dataset is required.");
    data=results;
    if (!selectedParticipant()) throw new Error("Prespecified default participant S01 is missing.");
    Object.values(controls).forEach((select) => {select.replaceChildren();select.disabled=false;});
    data.participants.forEach((p) => option(controls.participant,p.id,p.id));
    data.meta.channels.forEach((c) => option(controls.channel,c,c));
    Object.entries(data.meta.windows).forEach(([id,w]) => option(controls.window,id,`${w.start_ms}–${w.end_ms} ms`));
    data.meta.budgets.forEach((n) => option(controls.budget,n,`${n} + ${n}`));
    Object.entries(controls).forEach(([key,select]) => {
      select.value=String(state[key]);
      select.addEventListener("change",() => {state[key]=key==="budget" ? Number(select.value) : select.value;render();});
    });
    ["correlation-threshold","rms-threshold"].forEach((id) => $(id).addEventListener("input",thresholdChange));
    $("reset-thresholds").addEventListener("click",() => {$("correlation-threshold").value="0.8";$("rms-threshold").value="20";thresholdChange();});
    $("review-only").addEventListener("change",renderCohort);
    $("export-csv").disabled=false;
    $("export-csv").textContent="Export all 22 participants + rule (CSV)";
    $("export-csv").addEventListener("click",exportCSV);
    render();
  }
  Promise.resolve(window.TMS_ANALYSIS_READY).then(initialize).catch((error) => {
    const message="The analysis could not be displayed. Serve this folder over HTTP, or use the public site. No substitute or simulated results are shown. "+error.message;
    setText("readout",message); $("readout").classList.add("load-error");
    Object.values(controls).forEach((control) => {control.disabled=true;});
    $("export-csv").disabled=true;
    console.error(error);
  });
}());
