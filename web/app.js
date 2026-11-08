// Ek Baithak customer app — Team Matrix. Vanilla JS, no build step.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const inr = n => "₹" + Number(n || 0).toLocaleString("en-IN");

const T = {
  en: {
    tagline: "Accel Business · digital in one sitting", s1: "1 · Advisor", s2: "2 · Quote", s3: "3 · KYC", s4: "4 · Track",
    perday: "/ day", m12: "12 months", m24: "24 months · setup free", locked: "I'm locked in a contract with another provider",
    cluster: "Market lane code (Bazaar Cluster)", join: "Join", saathi: "Saathi code (if someone helped you)",
    buy: "Looks good — verify my business", consentH: "Before you upload anything",
    consentSub: "We only ask for what the law needs. Choose what you allow — you can withdraw any time from the tracker.",
    agree: "I agree — continue", snap: "Snap 4 documents", verify: "Verify instantly",
    specimen: "Demo: run a specimen applicant from the dataset", run: "Run",
    sim: "Demo clock — see what happens if installation runs late", delay: "Simulate a 4-day install crew delay", withdraw: "Withdraw consent & delete my documents",
    hello: "Namaste! Tell me about your business in one line — type or tap 🎤 and speak. Or answer a few quick taps.",
    example: "e.g. “kirana hai, 3 log, UPI aur CCTV chahiye, Jaipur”",
    placeholder: "Type or speak about your business…", done: "Done", skip: "I don't have GST",
    seePrice: "See my price", thinking: "Building your bundle…", gotIt: "Here is what fits your business:",
    placeOrder: "Place order", review: "Almost there — a specialist checks the flagged item within 2 hours. Your install slot is held.",
  },
  hi: {
    tagline: "Accel Business · एक बैठक में डिजिटल", s1: "1 · सलाह", s2: "2 · कीमत", s3: "3 · KYC", s4: "4 · ट्रैक",
    perday: "/ रोज़", m12: "12 महीने", m24: "24 महीने · सेटअप फ्री", locked: "मेरा दूसरी कंपनी से कॉन्ट्रैक्ट चल रहा है",
    cluster: "मार्केट गली कोड (बाज़ार क्लस्टर)", join: "जुड़ें", saathi: "साथी कोड (अगर किसी ने मदद की)",
    buy: "ठीक है — मेरा बिज़नेस वेरिफाई करें", consentH: "कुछ भी अपलोड करने से पहले",
    consentSub: "हम सिर्फ़ वही माँगते हैं जो कानून ज़रूरी बताता है। आप कभी भी ट्रैकर से सहमति वापस ले सकते हैं।",
    agree: "मैं सहमत हूँ — आगे बढ़ें", snap: "4 दस्तावेज़ों की फ़ोटो लें", verify: "तुरंत जाँचें",
    specimen: "डेमो: डेटासेट से नमूना आवेदक चलाएँ", run: "चलाएँ",
    sim: "डेमो घड़ी — देखें इंस्टॉलेशन लेट हो तो क्या होता है", delay: "इंस्टॉलेशन में 4 दिन की देरी दिखाएँ", withdraw: "सहमति वापस लें और दस्तावेज़ हटाएँ",
    hello: "नमस्ते! अपने बिज़नेस के बारे में एक लाइन में बताइए — लिखिए या 🎤 दबाकर बोलिए। या नीचे कुछ टैप कीजिए।",
    example: "जैसे “kirana hai, 3 log, UPI aur CCTV chahiye, Jaipur”",
    placeholder: "अपने बिज़नेस के बारे में लिखें या बोलें…", done: "हो गया", skip: "मेरे पास GST नहीं है",
    seePrice: "मेरी कीमत देखें", thinking: "आपका बंडल बन रहा है…", gotIt: "आपके बिज़नेस के लिए यह सही है:",
    placeOrder: "ऑर्डर करें", review: "बस थोड़ा सा — एक विशेषज्ञ 2 घंटे में जाँच करेगा। आपका इंस्टॉल स्लॉट बुक है।",
  },
};

const S = { lang: "en", qIdx: 0, questions: [], answers: { needs: [] }, result: null, consentId: null, order: null,
            remove: [], months: 12, cluster: null, docs: {} };
const t = k => T[S.lang][k] || T.en[k] || k;

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: opts.body && !(opts.body instanceof FormData) ? { "Content-Type": "application/json" } : {}, ...opts });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || r.statusText);
  return j;
}
function toast(msg) { const d = document.createElement("div"); d.className = "toast"; d.textContent = msg; document.body.appendChild(d); setTimeout(() => d.remove(), 2600); }

// ---------------------------------------------------------------- navigation
function go(step) {
  $$("main > section").forEach(s => s.classList.toggle("hidden", s.id !== step));
  $$("nav.steps button").forEach(b => b.classList.toggle("on", b.dataset.step === step));
  $(".composer")?.classList.toggle("hidden", step !== "advisor");
  window.scrollTo(0, 0);
}
function unlock(step) { $(`nav.steps button[data-step=${step}]`).disabled = false; }
$$("nav.steps button").forEach(b => b.onclick = () => !b.disabled && go(b.dataset.step));

function applyLang() {
  document.documentElement.lang = S.lang;
  $$("[data-t]").forEach(el => el.textContent = t(el.dataset.t));
  $("#langBtn").textContent = S.lang === "en" ? "हिं" : "EN";
  const inp = $("#composerInput"); if (inp) inp.placeholder = t("placeholder");
}
$("#langBtn").onclick = () => { S.lang = S.lang === "en" ? "hi" : "en"; S.langPicked = true; applyLang(); if (S.result) renderQuote(); };

// ---------------------------------------------------------------- advisor chat
function say(text, who = "bot") { const b = document.createElement("div"); b.className = `bubble ${who}`; b.innerHTML = text; $("#chat").appendChild(b); b.scrollIntoView({ behavior: "smooth", block: "end" }); return b; }
function chips(list, onPick, multi = false) {
  const wrap = document.createElement("div"); wrap.className = "chips";
  const picked = new Set();
  list.forEach(c => {
    const b = document.createElement("button"); b.className = "chip"; b.textContent = c;
    b.onclick = () => {
      if (multi) { picked.has(c) ? picked.delete(c) : picked.add(c); b.classList.toggle("on"); }
      else { wrap.remove(); onPick(c); }
    };
    wrap.appendChild(b);
  });
  if (multi) {
    const d = document.createElement("button"); d.className = "btn"; d.textContent = t("done");
    d.onclick = () => { wrap.remove(); onPick([...picked]); }; wrap.appendChild(d);
  }
  $("#chat").appendChild(wrap); wrap.scrollIntoView({ behavior: "smooth", block: "end" });
}

function askNext() {
  const q = S.questions[S.qIdx];
  if (!q) return runAdvisor();
  say(q[S.lang] || q.en);
  if (q.id === "needs") return chips(q.chips, picks => { say(picks.join(", ") || "—", "me"); S.answers.needs = picks; S.qIdx++; askNext(); }, true);
  if (q.id === "gstin") {
    S.awaitingGstin = true;
    return chips([t("skip")], () => { say(t("skip"), "me"); S.awaitingGstin = false; S.qIdx++; askNext(); });
  }
  chips(q.chips, c => { say(c, "me"); S.answers[q.id] = c; S.qIdx++; askNext(); });
}

async function runAdvisor(extra = {}) {
  const wait = say(`<span class="spinner"></span> ${t("thinking")}`);
  try {
    S.result = await api("/api/advise", { method: "POST", body: JSON.stringify(payload(extra)) });
    wait.remove();
    if (S.result.profile.language === "hi" && S.lang !== "hi") { S.lang = "hi"; applyLang(); }
    const lines = S.result.explanation.map(l => `• ${l}`).join("<br>");
    say(`<b>${t("gotIt")}</b><br>${lines}`);
    const btn = document.createElement("button"); btn.className = "btn block"; btn.textContent = `${t("seePrice")} → ${inr(S.result.quote.rozana_per_day)}${t("perday")}`;
    btn.onclick = () => { renderQuote(); unlock("quote"); go("quote"); };
    $("#chat").appendChild(btn); btn.scrollIntoView({ behavior: "smooth" });
  } catch (e) { wait.remove(); say("⚠️ " + e.message); }
}

function payload(extra = {}) {
  return { ...S.answers, remove: S.remove, contract_months: S.months, language: S.langPicked ? S.lang : null,
           locked_in: $("#lockedIn").checked, current_spend: +$("#spend").value || null,
           cluster_code: S.cluster?.code || null, ...extra };
}

function sendText() {
  const inp = $("#composerInput"); const text = inp.value.trim(); if (!text) return;
  inp.value = ""; say(text, "me");
  if (S.awaitingGstin) { S.answers.gstin = text; S.awaitingGstin = false; $(".chips:last-of-type")?.remove(); S.qIdx++; return askNext(); }
  S.answers = { ...S.answers, text }; $$(".chips").forEach(c => c.remove());
  runAdvisor();
}

function buildComposer() {
  const c = document.createElement("div"); c.className = "composer";
  c.innerHTML = `<input id="composerInput" autocomplete="off"><button class="btn ghost mic" id="micBtn" title="Speak">🎤</button><button class="btn" id="sendBtn">➤</button>`;
  document.body.appendChild(c);
  $("#sendBtn").onclick = sendText;
  $("#composerInput").onkeydown = e => e.key === "Enter" && sendText();
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { $("#micBtn").classList.add("hidden"); return; }
  $("#micBtn").onclick = () => {           // voice advisor: Hindi or English speech -> same parser
    const rec = new SR(); rec.lang = S.lang === "hi" ? "hi-IN" : "en-IN"; rec.interimResults = false;
    $("#micBtn").classList.add("live");
    rec.onresult = e => { $("#composerInput").value = e.results[0][0].transcript; sendText(); };
    rec.onend = () => $("#micBtn").classList.remove("live");
    rec.start();
  };
}

// ---------------------------------------------------------------- quote
async function recompute() {
  S.result = await api("/api/advise", { method: "POST", body: JSON.stringify(payload()) });
  renderQuote();
}

function renderQuote() {
  const r = S.result, q = r.quote, p = r.profile;
  $("#qProfile").textContent = `${p.business_type || p.segment_name} · ${p.employees} staff · ${p.sites} site(s) · ${p.city || "—"} (tier ${p.city_tier})`;
  $("#qDay").textContent = inr(q.rozana_per_day);
  $("#qMonth").innerHTML = `${inr(q.monthly_net)}/month + GST ${inr(q.gst)} = <b>${inr(q.monthly_total_incl_gst)}</b>` +
    (q.discount ? ` · One-Bill ${q.one_bill_discount_pct}%${q.bazaar_cluster_discount_pct ? ` + Cluster ${q.bazaar_cluster_discount_pct}%` : ""} off` : "") +
    `<br>Setup ${q.setup_waived ? `<s>${inr(q.setup_fee)}</s> <b>free</b>` : inr(q.setup_payable)} · Live by <b>${q.promise_date}</b>`;
  $$("[data-months]").forEach(b => b.classList.toggle("on", +b.dataset.months === S.months));

  const all = [...r.bundle.items.map(i => ({ ...i, on: true })),
               ...S.remove.map(id => ({ product_id: id, name: id, on: false, qty: "", unit_price: 0, why: "removed" }))];
  $("#qItems").innerHTML = all.map(i => `
    <div class="row"><div><div class="item-name">${i.name} ${i.qty ? "×" + i.qty : ""}</div><div class="item-why">${i.why}</div></div>
      <div style="text-align:right"><div>${i.on ? inr(i.unit_price * i.qty) : ""}</div>
      <label class="toggle"><input type="checkbox" data-pid="${i.product_id}" ${i.on ? "checked" : ""}><span></span></label></div></div>`).join("");
  $$("#qItems input").forEach(cb => cb.onchange = () => {
    const id = cb.dataset.pid;
    S.remove = cb.checked ? S.remove.filter(x => x !== id) : [...new Set([...S.remove, id])];
    recompute();
  });

  const ideas = [];
  const bs = q.bill_swap;
  ideas.push(`<div class="idea swap"><h4>Bill-Swap mirror <span class="pill green">save ${bs.saving_pct}%</span></h4>
    <p>Bought one by one from ${bs.vendors_replaced} vendors: ${inr(bs.separately_per_month)}/month. With one Accel bill: ${inr(q.monthly_net)}. You keep ${inr(bs.saving_per_month)} every month.</p></div>`);
  if (r.grow_ladder) ideas.push(`<div class="idea ladder"><h4>Grow Ladder <span class="pill amber">no GSTIN yet</span></h4>
    <p>Start today on this Lite bundle. ${r.grow_ladder.how} Unlocks: ${r.grow_ladder.unlocks.join(", ")} (${inr(r.grow_ladder.upgraded_monthly_net)}/month).</p></div>`);
  if (q.switch_shield_credit) ideas.push(`<div class="idea shield"><h4>Switch Shield <span class="pill red">${inr(q.switch_shield_credit)} credit</span></h4>
    <p>Locked in elsewhere? We credit ${inr(q.switch_shield_credit)} on your first Accel bill to cover the exit.</p></div>`);
  if (S.cluster) ideas.push(`<div class="idea cluster"><h4>Bazaar Cluster ${S.cluster.code} <span class="pill ${S.cluster.unlocked ? "green" : "red"}">${S.cluster.size} shop(s)</span></h4>
    <p>${S.cluster.unlocked ? `Group price unlocked: extra ${S.cluster.discount_pct}% off, one survey crew for the lane.` : `${S.cluster.needed} more shop(s) in your lane unlock ${S.cluster.discount_pct}% off for everyone. Share the code on WhatsApp.`}</p></div>`);
  $("#qIdeas").innerHTML = ideas.join("");

  const w = r.bundle.withheld;
  $("#qWithheld").classList.toggle("hidden", !w.length);
  $("#qWithheld").innerHTML = `<div class="muted" style="margin-bottom:4px">Not included, and why</div>` +
    w.map(x => `<div class="row"><div><div class="item-name">${x.name}</div><div class="item-why">${x.reason} — ${x.unlock}</div></div></div>`).join("");
}
$$("[data-months]").forEach(b => b.onclick = () => { S.months = +b.dataset.months; recompute(); });
$("#lockedIn").onchange = () => { $("#spendRow").classList.toggle("hidden", !$("#lockedIn").checked); recompute(); };
$("#spend").onchange = recompute;
$("#joinCluster").onclick = async () => {
  const code = $("#clusterCode").value.trim(); if (!code) return;
  const name = S.result.gstin?.trade_name || `Shop-${Math.random().toString(36).slice(2, 6)}`;
  S.cluster = await api("/api/cluster/join", { method: "POST", body: JSON.stringify({ code, business_name: name }) });
  recompute();
};
$("#toKyc").onclick = () => { unlock("kyc"); go("kyc"); };

// ---------------------------------------------------------------- consent + KYC
async function loadPurposes() {
  const d = await api("/api/consent/purposes");
  $("#purposes").innerHTML = Object.entries(d.purposes).map(([k, v]) => `
    <label><input type="checkbox" data-purpose="${k}" ${v.required ? "checked disabled" : ""}>
    <span>${v[S.lang] || v.en}${v.required ? ' <span class="pill dark">required</span>' : ' <span class="pill green">optional · off</span>'}</span></label>`).join("");
  $("#retention").textContent = d.retention;
}
$("#giveConsent").onclick = async () => {
  const purposes = Object.fromEntries($$("[data-purpose]").map(c => [c.dataset.purpose, c.checked]));
  const c = await api("/api/consent", { method: "POST", body: JSON.stringify({ purposes, language: S.lang }) });
  S.consentId = c.consent_id; toast(`Consent saved · ${c.consent_id}`);
  $("#consentCard").classList.add("hidden"); $("#uploadCard").classList.remove("hidden");
};
$$(".doc input").forEach(inp => inp.onchange = () => {
  const label = inp.closest(".doc"); S.docs[label.dataset.doc] = inp.files[0]; label.classList.add("ok");
});
$("#specimen").innerHTML = Array.from({ length: 12 }, (_, i) => `K${String(i + 1).padStart(2, "0")}`).map(k => `<option>${k}</option>`).join("");

async function showVerdict(promise) {
  $("#kycResult").innerHTML = `<div class="card"><span class="spinner"></span> OCR · GSTIN check digit · registry · cross-checks…</div>`;
  try {
    const v = await promise;
    const label = { APPROVED: "✅ APPROVED", NEEDS_REVIEW: "⏳ NEEDS REVIEW", REJECTED: "⛔ REJECTED" }[v.verdict];
    const f = v.fields.gst_certificate || {};
    $("#kycResult").innerHTML = `<div class="card"><div class="verdict ${v.verdict}">${label}</div>
      ${v.reasons.length ? `<div style="margin-bottom:8px">${v.reasons.map(r => `<div class="check"><b>!</b><span>${r}</span></div>`).join("")}</div>` : ""}
      <dl class="kv">${f.gstin ? `<dt>GSTIN</dt><dd>${f.gstin}</dd>` : ""}${f.trade_name ? `<dt>Business</dt><dd>${f.trade_name}</dd>` : ""}</dl>
      <details style="margin-top:8px"><summary class="muted">All ${v.checks.length} checks</summary>
      ${v.checks.map(c => `<div class="check"><b>${c.ok ? "✓" : c.severity === "reject" ? "✕" : "!"}</b><span><b>${c.check}</b> — ${c.detail}</span></div>`).join("")}</details>
      ${v.verdict !== "REJECTED" ? `<button class="btn block" id="placeOrder" style="margin-top:10px">${t("placeOrder")}</button>` : ""}
      ${v.verdict === "NEEDS_REVIEW" ? `<div class="muted" style="margin-top:6px">${t("review")}</div>` : ""}</div>`;
    S.kycName = f.trade_name;
    $("#placeOrder")?.addEventListener("click", placeOrder);
  } catch (e) { $("#kycResult").innerHTML = `<div class="card">⚠️ ${e.message}</div>`; }
}
$("#verifyBtn").onclick = () => {
  const fd = new FormData(); fd.append("consent_id", S.consentId);
  Object.entries(S.docs).forEach(([k, f]) => fd.append(k, f));
  showVerdict(api("/api/kyc/verify", { method: "POST", body: fd }));
};
$("#specimenBtn").onclick = () => showVerdict(api(`/api/kyc/specimen/${$("#specimen").value}?consent_id=${S.consentId}`, { method: "POST" }));

async function placeOrder() {
  S.order = await api("/api/orders", { method: "POST", body: JSON.stringify(payload({
    consent_id: S.consentId, saathi_code: $("#saathiCode").value.trim() || null, business_name: S.kycName || null })) });
  unlock("track"); go("track"); renderTrack();
}

// ---------------------------------------------------------------- tracker
async function renderTrack() {
  const day = +$("#dayRange").value;
  const delay = $("#delayToggle").checked ? 4 : 0;
  const o = await api(`/api/orders/${S.order.order_id}?day=${day}&delay=${delay}`);
  $("#dayLabel").textContent = `Day ${day} after order (${o.as_of})`;
  const pill = o.status === "Live" ? "green" : o.late_days ? "red" : "amber";
  $("#trackCard").innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center"><b>${o.business_name}</b><span class="pill ${pill}">${o.status}</span></div>
    <div class="muted">${o.order_id} · consent ${o.consent_id}</div>
    <div style="margin:10px 0"><span class="muted">Promised live by</span><div class="price"><span class="big" style="font-size:24px">${o.promise_date}</span></div></div>
    ${o.late_days ? `<div class="idea shield"><h4>Late by ${o.late_days} day(s) <span class="pill red">${inr(o.late_credit_inr)} credit</span></h4><p>Credited to your next bill automatically. No need to call.</p></div>` : ""}
    ${o.switch_shield_credit ? `<div class="idea shield"><h4>Switch Shield <span class="pill red">${inr(o.switch_shield_credit)}</span></h4><p>On your first bill.</p></div>` : ""}
    <div class="timeline">${o.steps.map(s => `<div class="tl ${s.done ? "done" : ""}">${s.step}<small>${s.done ? "Done" : "Due"} · ${s.due}</small></div>`).join("")}</div>`;
}
$("#dayRange").oninput = () => S.order && renderTrack();
$("#delayToggle").onchange = () => S.order && renderTrack();
$("#withdrawBtn").onclick = async () => {
  if (!S.consentId) return;
  await api(`/api/consent/${S.consentId}/withdraw`, { method: "POST" });
  toast("Consent withdrawn · document images deleted");
};

// ---------------------------------------------------------------- start
(async function init() {
  buildComposer(); applyLang();
  const qs = new URLSearchParams(location.search); if (qs.get("saathi")) $("#saathiCode").value = qs.get("saathi");
  S.questions = await api("/api/questions");
  say(`${t("hello")}<br><span class="muted">${t("example")}</span>`);
  askNext(); loadPurposes();
})();
