/* ============================================================
   NutriSage AI — Frontend Logic
   Tabs · Chat · BMI · Meal Plan · Family · Analyzer
   ============================================================ */

"use strict";

// ── State ────────────────────────────────────────────────────
const state = {
  chatHistory:   [],
  familyMembers: [],
  darkMode:      false,
  memberCounter: 0,
};

// ── DOM helpers ──────────────────────────────────────────────
const $  = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

function showToast(msg, type = "info") {
  const toast = $("#nsToast");
  const body  = $("#toastMsg");
  body.textContent = msg;
  toast.classList.remove("bg-success", "bg-danger", "bg-warning");
  if (type === "success") toast.classList.add("bg-success");
  if (type === "error")   toast.classList.add("bg-danger");
  if (type === "warning") toast.classList.add("bg-warning");
  bootstrap.Toast.getOrCreateInstance(toast, { delay: 3500 }).show();
}

function spinner(label = "Generating with AI…") {
  return `<div class="ns-spinner-wrap">
    <div class="spinner-border spinner-border-sm text-accent" role="status"></div>
    <span>${label}</span>
  </div>`;
}

/** Convert basic markdown-ish text → safe HTML for display */
function formatAIText(text) {
  if (!text) return "";
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    // bold
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/__(.+?)__/g, "<strong>$1</strong>")
    // italic
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    // code
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    // headings
    .replace(/^### (.+)$/gm, "<h5 class='mt-3 mb-1 fw-600'>$1</h5>")
    .replace(/^## (.+)$/gm,  "<h4 class='mt-3 mb-1 fw-600'>$1</h4>")
    .replace(/^# (.+)$/gm,   "<h3 class='mt-3 mb-2 fw-600'>$1</h3>")
    // bullet lists
    .replace(/^[\-\*] (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>)/s,  "<ul class='ps-3 mt-1'>$1</ul>")
    // numbered lists
    .replace(/^\d+\. (.+)$/gm, "<li>$1</li>")
    // line breaks
    .replace(/\n{2,}/g, "<br/><br/>")
    .replace(/\n/g, "<br/>");
}

// ── API helpers ───────────────────────────────────────────────
async function apiFetch(endpoint, body) {
  const res = await fetch(endpoint, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: "Request failed" }));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Status polling ────────────────────────────────────────────
async function checkStatus() {
  try {
    const data = await fetch("/api/status").then(r => r.json());
    const badge = $("#statusBadge");
    if (data.watsonx_connected) {
      badge.className = "badge ns-status-badge";
      badge.innerHTML = `<span class="ns-dot"></span> Live · ${data.model.split("/")[1] || data.model}`;
    } else {
      badge.className = "badge ns-status-badge demo";
      badge.innerHTML = `<span class="ns-dot"></span> Demo Mode`;
    }
  } catch {
    const badge = $("#statusBadge");
    badge.className = "badge ns-status-badge error";
    badge.innerHTML = `<span class="ns-dot"></span> Offline`;
  }
}

// ── Dark Mode ─────────────────────────────────────────────────
function initDarkMode() {
  const saved = localStorage.getItem("ns-dark");
  if (saved === "true") applyDark(true);

  $("#darkToggle").addEventListener("click", () => {
    state.darkMode = !state.darkMode;
    applyDark(state.darkMode);
    localStorage.setItem("ns-dark", state.darkMode);
  });
}

function applyDark(on) {
  document.documentElement.setAttribute("data-bs-theme", on ? "dark" : "light");
  state.darkMode = on;
  const btn = $("#darkToggle");
  btn.innerHTML = on
    ? '<i class="bi bi-sun-fill"></i>'
    : '<i class="bi bi-moon-stars-fill"></i>';
}

// ── Tab Switching ─────────────────────────────────────────────
function initTabs() {
  document.addEventListener("click", e => {
    const btn = e.target.closest("[data-tab]");
    if (!btn) return;
    const tab = btn.dataset.tab;

    // Update all buttons (sidebar + mobile bar + offcanvas)
    $$("[data-tab]").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));

    // Show correct content panel
    $$(".ns-tab-content").forEach(p => p.classList.remove("active"));
    const panel = $(`#tab-${tab}`);
    if (panel) panel.classList.add("active");

    // Close offcanvas if open
    const oc = document.getElementById("mobileMenu");
    if (oc) bootstrap.Offcanvas.getInstance(oc)?.hide();
  });
}

// ── CHAT ─────────────────────────────────────────────────────
function initChat() {
  const chatArea = $("#chatMessages");
  const input    = $("#chatInput");
  const sendBtn  = $("#sendBtn");
  const clearBtn = $("#clearChat");
  const charCount = $("#charCount");

  // Character counter
  input.addEventListener("input", () => {
    charCount.textContent = input.value.length;
  });

  // Ctrl+Enter to send
  input.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault(); sendMessage();
    }
  });

  sendBtn.addEventListener("click", sendMessage);

  // Suggestion chips
  document.addEventListener("click", e => {
    const chip = e.target.closest(".ns-suggestion-chip");
    if (!chip) return;
    input.value = chip.dataset.msg || "";
    charCount.textContent = input.value.length;
    sendMessage();
    // Hide suggestions after first use
    const sugg = $("#chatSuggestions");
    if (sugg) sugg.style.display = "none";
  });

  clearBtn.addEventListener("click", () => {
    state.chatHistory = [];
    chatArea.innerHTML = "";
    const sugg = $("#chatSuggestions");
    if (sugg) sugg.style.display = "";
    charCount.textContent = 0;
    input.value = "";
  });

  // Welcome message
  appendMessage("assistant",
    `👋 Hi! I'm **NutriSage AI**, your personal Indian nutrition expert powered by **IBM Watsonx.ai**.\n\n` +
    `I can help you with:\n` +
    `- 🥗 Personalised meal plans\n` +
    `- 🔢 Calorie & macro analysis\n` +
    `- 🇮🇳 Indian food recommendations\n` +
    `- 👨‍👩‍👧 Family diet planning\n\n` +
    `What would you like help with today?`
  );

  async function sendMessage() {
    const msg = input.value.trim();
    if (!msg) return;

    input.value = "";
    charCount.textContent = 0;
    appendMessage("user", msg);

    // Add to history
    state.chatHistory.push({ role: "user", content: msg });

    // Typing indicator
    const typingId = appendTyping();

    try {
      const data = await apiFetch("/api/chat", {
        message:        msg,
        history:        state.chatHistory.slice(-8),
        family_context: { members: state.familyMembers },
      });

      removeTyping(typingId);
      appendMessage("assistant", data.response);
      state.chatHistory.push({ role: "assistant", content: data.response });

    } catch (err) {
      removeTyping(typingId);
      appendMessage("assistant", `⚠️ Error: ${err.message}. Please try again.`);
    }
    scrollChat();
  }

  function appendMessage(role, text) {
    const isUser = role === "user";
    const div    = document.createElement("div");
    div.className = `ns-msg ${role}`;
    div.innerHTML = `
      <div class="ns-msg-avatar">${isUser ? '<i class="bi bi-person-fill"></i>' : '<i class="bi bi-robot"></i>'}</div>
      <div>
        <div class="ns-msg-bubble">${formatAIText(text)}</div>
        <div class="ns-timestamp">${new Date().toLocaleTimeString()}</div>
      </div>`;
    chatArea.appendChild(div);
    scrollChat();
    return div;
  }

  function appendTyping() {
    const id  = "typing-" + Date.now();
    const div = document.createElement("div");
    div.id        = id;
    div.className = "ns-msg assistant";
    div.innerHTML = `
      <div class="ns-msg-avatar"><i class="bi bi-robot"></i></div>
      <div class="ns-msg-bubble">
        <div class="ns-typing-dots"><span></span><span></span><span></span></div>
      </div>`;
    chatArea.appendChild(div);
    scrollChat();
    return id;
  }

  function removeTyping(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }
}

function scrollChat() {
  const area = $("#chatMessages");
  if (area) area.scrollTop = area.scrollHeight;
}

// ── DASHBOARD ─────────────────────────────────────────────────
function initDashboard() {
  $("#calcDashboard").addEventListener("click", async () => {
    const w = parseFloat($("#db-weight").value);
    const h = parseFloat($("#db-height").value);
    const a = parseInt($("#db-age").value);
    const g = $("#db-gender").value;
    const act = $("#db-activity").value;

    if (!w || !h || !a) { showToast("Please fill weight, height, and age", "warning"); return; }

    const btn = $("#calcDashboard");
    btn.disabled = true;
    btn.innerHTML = spinner("Calculating…");

    try {
      const data = await apiFetch("/api/bmi", { weight: w, height: h, age: a, gender: g, activity: act });

      // Update stat cards
      $("#stat-calories").textContent = data.tdee ?? data.maintenance ?? "—";
      $("#stat-water").textContent = Math.round((w * 0.033)).toString();
      $("#stat-protein").textContent = Math.round(w * 1.6).toString();
      $("#stat-bmi").textContent = data.bmi ?? "—";
      $("#stat-bmi").style.color = data.color || "";

      // Macro breakdown
      renderMacroBars(data.tdee ?? data.maintenance ?? 2000);

      // AI Tips
      const tipsDiv = $("#aiTipsPanel");
      tipsDiv.innerHTML = `<div class="ns-result-area">${formatAIText(data.ai_tips || "No tips available.")}</div>`;

    } catch (err) {
      showToast("Calculation failed: " + err.message, "error");
    }

    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-calculator me-1"></i>Calculate My Numbers';
  });
}

function renderMacroBars(calories) {
  const protein = Math.round((calories * 0.3) / 4);   // 30% protein, 4 kcal/g
  const carbs   = Math.round((calories * 0.45) / 4);  // 45% carbs
  const fat     = Math.round((calories * 0.25) / 9);  // 25% fat, 9 kcal/g

  const bars = [
    { label: "Protein",      val: protein, max: 200, unit: "g", color: "#3b82d4" },
    { label: "Carbohydrates",val: carbs,   max: 350, unit: "g", color: "#22c55e" },
    { label: "Fat",          val: fat,     max: 100, unit: "g", color: "#f59e0b" },
  ];

  const wrap = $("#macroBreakdown");
  wrap.innerHTML = bars.map(b => `
    <div class="ns-progress-row mb-3">
      <div class="ns-macro-label">
        <span>${b.label}</span><span style="color:${b.color}">${b.val}${b.unit}</span>
      </div>
      <div class="ns-progress-bar-track">
        <div class="ns-progress-bar-fill" style="width:${Math.min(100,(b.val/b.max)*100).toFixed(1)}%;background:${b.color}"></div>
      </div>
    </div>`).join("") +
    `<p class="text-muted mt-3" style="font-size:.8rem">Based on ${calories} kcal/day target (30/45/25 split)</p>`;
}

// ── MEAL PLAN ─────────────────────────────────────────────────
function initMealPlan() {
  $("#generatePlan").addEventListener("click", async () => {
    const fields = {
      weight:    parseFloat($("#mp-weight").value),
      height:    parseFloat($("#mp-height").value),
      age:       parseInt($("#mp-age").value),
      gender:    $("#mp-gender").value,
      activity:  $("#mp-activity").value,
      goal:      $("#mp-goal").value,
      diet_type: $("#mp-diet").value,
      cuisine:   $("#mp-cuisine").value,
      allergies: $("#mp-allergies").value || "none",
    };

    if (!fields.weight || !fields.height || !fields.age) {
      showToast("Please fill weight, height, and age", "warning"); return;
    }

    const result = $("#mealPlanResult");
    const btn    = $("#generatePlan");
    result.innerHTML = spinner("Building your 7-day meal plan…");
    btn.disabled = true;

    try {
      const data = await apiFetch("/api/nutrition-plan", fields);

      result.innerHTML = `
        <div class="row g-3 mb-3">
          <div class="col-md-3 col-6">
            <div class="ns-stat-card text-center">
              <div class="ns-stat-value" style="color:${data.bmi.color}">${data.bmi.bmi}</div>
              <div class="ns-stat-label">BMI — ${data.bmi.category}</div>
            </div>
          </div>
          <div class="col-md-3 col-6">
            <div class="ns-stat-card text-center">
              <div class="ns-stat-value">${data.tdee.bmr}</div>
              <div class="ns-stat-label">BMR (kcal/day)</div>
            </div>
          </div>
          <div class="col-md-3 col-6">
            <div class="ns-stat-card text-center">
              <div class="ns-stat-value">${data.target_calories}</div>
              <div class="ns-stat-label">Daily Target (kcal)</div>
            </div>
          </div>
          <div class="col-md-3 col-6">
            <div class="ns-stat-card text-center">
              <div class="ns-stat-value">${data.tdee.tdee}</div>
              <div class="ns-stat-label">TDEE (kcal)</div>
            </div>
          </div>
        </div>
        <div class="ns-result-area">${formatAIText(data.plan)}</div>`;

      showToast("Meal plan generated!", "success");
    } catch (err) {
      result.innerHTML = `<div class="alert alert-danger">Error: ${err.message}</div>`;
    }
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-magic me-1"></i>Generate My 7-Day Meal Plan';
  });
}

// ── BMI CALCULATOR ────────────────────────────────────────────
function initBMI() {
  $("#calcBmi").addEventListener("click", async () => {
    const w   = parseFloat($("#bmi-weight").value);
    const h   = parseFloat($("#bmi-height").value);
    const age = parseInt($("#bmi-age").value);
    const g   = $("#bmi-gender").value;
    const act = $("#bmi-activity").value;

    if (!w || !h || !age) { showToast("Please fill weight, height, and age", "warning"); return; }

    const resultDiv = $("#bmiResult");
    const btn       = $("#calcBmi");
    resultDiv.innerHTML = `<div class="ns-card-header"><i class="bi bi-bar-chart me-2 text-accent"></i>Your Results</div>${spinner("Analysing & getting AI tips…")}`;
    btn.disabled = true;

    try {
      const d = await apiFetch("/api/bmi", { weight: w, height: h, age, gender: g, activity: act });

      const bmiBars = [
        { range: "Underweight", min: 0,    max: 18.5, color: "#3b82d4" },
        { range: "Healthy",     min: 18.5, max: 25,   color: "#22c55e" },
        { range: "Overweight",  min: 25,   max: 30,   color: "#f59e0b" },
        { range: "Obese",       min: 30,   max: 40,   color: "#ef4444" },
      ];

      const calEntries = [
        ["Maintenance", d.maintenance ?? d.tdee],
        ["Weight Loss (−500)",  d.weight_loss],
        ["Weight Gain (+500)",  d.weight_gain],
      ];

      resultDiv.innerHTML = `
        <div class="ns-card-header"><i class="bi bi-bar-chart me-2 text-accent"></i>Your Results</div>
        <div class="p-3">
          <div class="ns-bmi-gauge-wrap">
            <div class="ns-bmi-number" style="color:${d.color}">${d.bmi}</div>
            <div class="ns-bmi-cat" style="color:${d.color}">${d.category}</div>
          </div>
          <div class="ns-divider"></div>
          <div class="row g-2 mb-3">
            ${calEntries.map(([lbl, val]) => `
              <div class="col-4 text-center">
                <div style="font-size:1.2rem;font-weight:700">${val}</div>
                <div style="font-size:.72rem;color:var(--ns-muted)">${lbl}</div>
              </div>`).join("")}
          </div>
          <div class="ns-divider"></div>
          <div id="bmi-bars" class="mb-3">
            ${bmiBars.map(b => {
              const pct = Math.min(100, Math.max(0, ((d.bmi - b.min)/(b.max - b.min))*100));
              const active = d.bmi >= b.min && d.bmi < b.max;
              return `<div class="ns-progress-row">
                <div class="ns-macro-label">
                  <span${active ? ` style="font-weight:700;color:${b.color}"` : ""}>${b.range}${active ? " ✓" : ""}</span>
                  <span style="font-size:.75rem">${b.min}–${b.max === 40 ? "40+" : b.max}</span>
                </div>
                <div class="ns-progress-bar-track">
                  <div class="ns-progress-bar-fill" style="width:${active ? pct.toFixed(0) : 0}%;background:${b.color}"></div>
                </div>
              </div>`;
            }).join("")}
          </div>
          <div class="ns-divider"></div>
          <h6 class="fw-600 mb-2"><i class="bi bi-lightbulb me-1 text-accent"></i>AI Nutrition Tips</h6>
          <div class="ns-result-area" style="max-height:220px;overflow-y:auto">${formatAIText(d.ai_tips)}</div>
        </div>`;

      showToast("BMI calculated!", "success");
    } catch (err) {
      resultDiv.innerHTML = `<div class="ns-card-header">Error</div><div class="p-3 text-danger">${err.message}</div>`;
    }
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-calculator me-1"></i>Calculate BMI & Get AI Tips';
  });
}

// ── FAMILY PLANNER ────────────────────────────────────────────
function initFamily() {
  renderFamilyMembers(); // initial empty state

  $("#addMemberBtn").addEventListener("click", () => {
    if (state.familyMembers.length >= 8) {
      showToast("Maximum 8 family members allowed", "warning"); return;
    }
    state.familyMembers.push({
      id:     ++state.memberCounter,
      name:   "",
      age:    "",
      gender: "male",
      diet:   "balanced",
      goals:  "healthy eating",
    });
    renderFamilyMembers();
  });

  $("#generateFamilyPlan").addEventListener("click", async () => {
    // Sync inputs to state
    syncFamilyInputs();
    const valid = state.familyMembers.filter(m => m.name && m.age);
    if (!valid.length) {
      showToast("Add at least one family member with name and age", "warning"); return;
    }

    const result = $("#familyPlanResult");
    const btn    = $("#generateFamilyPlan");
    result.innerHTML = spinner("Creating your family meal plan…");
    btn.disabled = true;

    try {
      const data = await apiFetch("/api/family-plan", { members: valid });
      result.innerHTML = `<div class="ns-result-area">${formatAIText(data.family_plan)}</div>`;
      showToast("Family plan ready!", "success");
    } catch (err) {
      result.innerHTML = `<div class="alert alert-danger">Error: ${err.message}</div>`;
    }
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-magic me-1"></i>Generate Family Meal Plan';
  });
}

function renderFamilyMembers() {
  const container = $("#familyMembers");
  if (!state.familyMembers.length) {
    container.innerHTML = `<div class="col-12 text-muted text-center py-3">
      No family members yet. Click <strong>Add Member</strong> to get started.
    </div>`;
    return;
  }

  container.innerHTML = state.familyMembers.map(m => `
    <div class="col-md-6 col-lg-4">
      <div class="ns-member-card" data-id="${m.id}">
        <button class="ns-remove-btn" data-remove="${m.id}" title="Remove">
          <i class="bi bi-x-circle-fill"></i>
        </button>
        <h6 class="fw-600 mb-3"><i class="bi bi-person-circle text-accent me-1"></i>Member #${m.id}</h6>
        <div class="row g-2">
          <div class="col-12">
            <label class="ns-label">Name</label>
            <input type="text" class="form-control ns-input ns-member-name" data-field="name" value="${m.name}"
              placeholder="e.g. Priya" data-id="${m.id}" />
          </div>
          <div class="col-6">
            <label class="ns-label">Age</label>
            <input type="number" class="form-control ns-input" data-field="age" value="${m.age}"
              placeholder="Age" data-id="${m.id}" />
          </div>
          <div class="col-6">
            <label class="ns-label">Gender</label>
            <select class="form-select ns-input" data-field="gender" data-id="${m.id}">
              <option value="male" ${m.gender === "male" ? "selected" : ""}>Male</option>
              <option value="female" ${m.gender === "female" ? "selected" : ""}>Female</option>
            </select>
          </div>
          <div class="col-12">
            <label class="ns-label">Diet Type</label>
            <select class="form-select ns-input" data-field="diet" data-id="${m.id}">
              ${["balanced","vegetarian","vegan","keto","diabetic"].map(d =>
                `<option value="${d}" ${m.diet===d?"selected":""}>${d.charAt(0).toUpperCase()+d.slice(1)}</option>`
              ).join("")}
            </select>
          </div>
          <div class="col-12">
            <label class="ns-label">Health Goals</label>
            <input type="text" class="form-control ns-input" data-field="goals" value="${m.goals}"
              placeholder="e.g. weight loss" data-id="${m.id}" />
          </div>
        </div>
      </div>
    </div>`).join("");

  // Remove buttons
  container.addEventListener("click", e => {
    const btn = e.target.closest("[data-remove]");
    if (!btn) return;
    const id = parseInt(btn.dataset.remove);
    state.familyMembers = state.familyMembers.filter(m => m.id !== id);
    renderFamilyMembers();
  });
}

function syncFamilyInputs() {
  const container = $("#familyMembers");
  state.familyMembers.forEach(m => {
    const card = container.querySelector(`[data-id="${m.id}"]`);
    if (!card) return;
    card.querySelectorAll("[data-field]").forEach(inp => {
      m[inp.dataset.field] = inp.value;
    });
  });
}

// ── MEAL ANALYZER ─────────────────────────────────────────────
function initAnalyzer() {
  $("#analyzeMealBtn").addEventListener("click", async () => {
    const meal    = $("#meal-desc").value.trim();
    const portion = $("#meal-portion").value.trim() || "1 serving";
    if (!meal) { showToast("Please describe your meal", "warning"); return; }

    const result = $("#analyzeResult");
    const btn    = $("#analyzeMealBtn");
    result.innerHTML = spinner("Analysing nutritional content…");
    btn.disabled = true;

    try {
      const data = await apiFetch("/api/analyze-meal", { meal, portion });
      result.innerHTML = `
        <div class="ns-card">
          <div class="ns-card-header"><i class="bi bi-clipboard2-data me-2 text-accent"></i>Analysis: ${escHtml(meal)}</div>
          <div class="p-3 ns-result-area">${formatAIText(data.analysis)}</div>
        </div>`;
      showToast("Analysis complete!", "success");
    } catch (err) {
      result.innerHTML = `<div class="alert alert-danger">Error: ${err.message}</div>`;
    }
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-search me-1"></i>Analyze Meal';
  });
}

function escHtml(str) {
  return str.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

// ── INIT ──────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initDarkMode();
  initTabs();
  initChat();
  initDashboard();
  initMealPlan();
  initBMI();
  initFamily();
  initAnalyzer();
  checkStatus();
  // Poll status every 60 seconds
  setInterval(checkStatus, 60_000);
});
