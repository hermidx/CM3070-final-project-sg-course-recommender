const API = "http://localhost:8000";

// --------------------
// ✅ user_id (no login)
// --------------------
function getUserId() {
  let uid = localStorage.getItem("user_id");
  if (!uid) {
    uid =
      (window.crypto && crypto.randomUUID && crypto.randomUUID()) ||
      `uid_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    localStorage.setItem("user_id", uid);
  }
  return uid;
}

// --------------------
// DOM refs (guarded)
// --------------------
const elType = document.getElementById("institutionType");
const elLevel = document.getElementById("level");
const elInst = document.getElementById("institution");
const elQuery = document.getElementById("query");
const elBtn = document.getElementById("btn");
const elMsg = document.getElementById("msg");
const elResults = document.getElementById("results");

const elUseSemantic = document.getElementById("useSemantic");
const elUseHybrid = document.getElementById("useHybrid");

const elRequiresMath = document.getElementById("requiresMath");
const elRequiresEnglish = document.getElementById("requiresEnglish");

// Saved UI
const elBtnSaved = document.getElementById("btnSaved");
const elSavedPanel = document.getElementById("savedPanel");

// Compare UI
const elCompareBar = document.getElementById("compareBar");
const elCompareCount = document.getElementById("compareCount");
const elBtnCompare = document.getElementById("btnCompare");
const elBtnClearCompare = document.getElementById("btnClearCompare");
const elComparePanel = document.getElementById("comparePanel");

// --------------------
// State
// --------------------
let lastResults = [];
let lastUiMeta = null;
let lastNoteText = "";

const compareSelected = new Map();
const MAX_COMPARE = 3;

let savedIds = new Set();
let showingSaved = false;
let lastQueryText = "";

// --------------------
// Helpers
// --------------------
function setMsg(text) {
  if (!elMsg) return;
  elMsg.textContent = text || "";
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function isNil(v) {
  if (v === null || v === undefined) return true;
  const s = String(v).trim();
  if (s === "") return true;
  const low = s.toLowerCase();
  return low === "nil" || low === "n/a" || low === "na" || low === "none";
}

function fmt(v) {
  return isNil(v) ? "" : String(v).trim();
}

function showOrDash(v) {
  return isNil(v) ? "—" : String(v).trim();
}

function setOptions(select, options) {
  if (!select) return;
  select.innerHTML = "";

  const all = document.createElement("option");
  all.value = "All";
  all.textContent = "All";
  select.appendChild(all);

  (options || []).forEach((v) => {
    const s = String(v || "").trim();
    if (!s) return;
    const o = document.createElement("option");
    o.value = s;
    o.textContent = s;
    select.appendChild(o);
  });
}

function courseKey(r) {
  return r.url && String(r.url).trim()
    ? String(r.url).trim()
    : `${r.course_name}@@${r.institution}`;
}

function renderWhyMatched(r) {
  const items = Array.isArray(r.why_matched) ? r.why_matched : [];
  if (!items.length) return "";

  const pills = items
    .map((x) => `<span class="why-pill">${escapeHtml(String(x))}</span>`)
    .join("");

  return `
    <div class="whyMatched">
      <div class="sectionTitle">Why this matched</div>
      <div class="whyPills">${pills}</div>
    </div>
  `;
}

function renderMissingFields(r) {
  const items = Array.isArray(r.missing_fields) ? r.missing_fields : [];
  if (!items.length) return "";

  return `
    <div class="missingInfo">
      <span class="missingLabel">Some details are missing:</span>
      ${items
        .map(
          (x) => `<span class="missing-pill">${escapeHtml(String(x))}</span>`
        )
        .join("")}
    </div>
  `;
}

function renderSearchSummary(uiMeta, noteText) {
  if (!uiMeta) {
    return noteText
      ? `<div class="searchSummary"><div class="summaryNote">${escapeHtml(
          noteText
        )}</div></div>`
      : "";
  }

  const mode = uiMeta.mode ? String(uiMeta.mode).toUpperCase() : "SEARCH";
  const count = Number(uiMeta.result_count || 0);
  const personalised = !!uiMeta.personalised;

  return `
    <div class="searchSummary">
      <div class="summaryTop">
        <span class="modeBadge">${escapeHtml(mode)}</span>
        ${
          personalised
            ? `<span class="modeBadge personalBadge">PERSONALISED</span>`
            : ""
        }
        <span class="resultCount">${count} result${
    count === 1 ? "" : "s"
  }</span>
      </div>
      ${
        noteText ? `<div class="summaryNote">${escapeHtml(noteText)}</div>` : ""
      }
    </div>
  `;
}

// --------------------
// Load meta
// --------------------
async function loadMeta() {
  try {
    const res = await fetch(`${API}/api/meta`, { mode: "cors" });
    if (!res.ok) throw new Error(await res.text());
    const meta = await res.json();
    setOptions(elType, meta.institution_types);
    setOptions(elLevel, meta.levels);
    setOptions(elInst, meta.institutions);
  } catch (e) {
    console.error(e);
    setMsg("Could not load filters (meta). Is backend running on :8000?");
  }
}

// --------------------
// Events logging
// --------------------
async function logEvent(courseId, eventType, queryText = "") {
  const userId = getUserId();
  if (!courseId) return;

  try {
    await fetch(`${API}/events`, {
      method: "POST",
      mode: "cors",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        course_id: courseId,
        event_type: eventType,
        query: queryText || "",
      }),
    });
  } catch (e) {
    console.warn("Event log failed:", e);
  }
}

// --------------------
// Feedback
// --------------------
async function sendFeedback(courseId, rating, comment = "") {
  const userId = getUserId();
  if (!courseId) return false;

  try {
    const res = await fetch(`${API}/feedback`, {
      method: "POST",
      mode: "cors",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        course_id: courseId,
        rating: rating,
        comment: comment || "",
      }),
    });

    if (!res.ok) {
      console.error(await res.text());
      setMsg("Feedback failed.");
      return false;
    }
    return true;
  } catch (e) {
    console.error(e);
    setMsg("Feedback failed (network error).");
    return false;
  }
}

// --------------------
// Saved helpers
// --------------------
async function fetchSavedIds() {
  const userId = getUserId();
  const res = await fetch(
    `${API}/user/saved?user_id=${encodeURIComponent(userId)}`,
    { method: "GET", mode: "cors" }
  );
  if (!res.ok) throw new Error("Failed to fetch saved IDs");
  const data = await res.json();
  return data.saved || [];
}

async function refreshSavedIds() {
  const ids = await fetchSavedIds();
  savedIds = new Set(ids);
  return ids;
}

async function fetchSavedDetailsForUser() {
  const userId = getUserId();
  const res = await fetch(
    `${API}/user/saved/details?user_id=${encodeURIComponent(userId)}`,
    { method: "GET", mode: "cors" }
  );
  if (!res.ok) throw new Error("Failed to fetch saved details");
  return await res.json();
}

async function saveCourse(courseId) {
  const userId = getUserId();
  if (!courseId) return false;

  try {
    const res = await fetch(`${API}/user/save`, {
      method: "POST",
      mode: "cors",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, course_id: courseId }),
    });

    if (!res.ok) {
      console.error(await res.text());
      setMsg("Save failed.");
      return false;
    }

    savedIds.add(courseId);
    setMsg("✅ Saved! (View it in ⭐ My Saved Courses)");
    return true;
  } catch (err) {
    console.error(err);
    setMsg("Save failed (network error).");
    return false;
  }
}

async function removeSavedCourse(courseId) {
  const userId = getUserId();
  if (!courseId) throw new Error("No course_id");

  const res = await fetch(`${API}/user/saved/remove`, {
    method: "POST",
    mode: "cors",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, course_id: courseId }),
  });

  if (!res.ok) {
    console.error(await res.text());
    throw new Error("Remove failed");
  }

  savedIds.delete(courseId);
  return await res.json();
}

// --------------------
// View toggles
// --------------------
function showSearchView() {
  showingSaved = false;
  if (elBtnSaved) elBtnSaved.textContent = "⭐ My Saved Courses";

  if (elSavedPanel) elSavedPanel.style.display = "none";
  if (elResults) elResults.style.display = "block";

  updateCompareBar();
}

function showSavedView() {
  showingSaved = true;
  if (elBtnSaved) elBtnSaved.textContent = "🔎 Back to Search";

  if (elSavedPanel) elSavedPanel.style.display = "block";
  if (elResults) elResults.style.display = "none";

  if (elCompareBar) elCompareBar.style.display = "none";
  if (elComparePanel) {
    elComparePanel.style.display = "none";
    elComparePanel.innerHTML = "";
  }
  compareSelected.clear();
}

// --------------------
// Compare
// --------------------
function updateCompareBar() {
  if (showingSaved) return;
  if (!elCompareBar || !elCompareCount || !elComparePanel) return;

  const n = compareSelected.size;
  elCompareCount.textContent = String(n);
  elCompareBar.style.display = n > 0 ? "flex" : "none";

  elComparePanel.style.display = "none";
  elComparePanel.innerHTML = "";
}

function toggleCompare(r, checked) {
  const key = courseKey(r);
  if (checked) {
    if (compareSelected.size >= MAX_COMPARE) {
      setMsg(`You can compare up to ${MAX_COMPARE} courses.`);
      return false;
    }
    compareSelected.set(key, r);
  } else {
    compareSelected.delete(key);
  }
  updateCompareBar();
  return true;
}

function renderComparePanel() {
  if (!elComparePanel) return;

  const items = Array.from(compareSelected.values());
  if (items.length < 2) {
    setMsg("Select at least 2 courses to compare.");
    return;
  }

  const rows = [
    { label: "Course", get: (x) => showOrDash(x.course_name) },
    { label: "Institution", get: (x) => showOrDash(x.institution) },
    { label: "Type", get: (x) => showOrDash(x.institution_type) },
    { label: "Level", get: (x) => showOrDash(x.level) },
    { label: "Skills", get: (x) => showOrDash(x.skills) },
    { label: "Duration", get: (x) => showOrDash(x.duration) },
    { label: "Fees", get: (x) => showOrDash(x.fees) },
    { label: "Prerequisites", get: (x) => showOrDash(x.prerequisites) },
    {
      label: "Entry requirements",
      get: (x) => showOrDash(x.entry_requirements),
    },
    {
      label: "Match score",
      get: (x) =>
        isNil(x.match_score) ? "—" : `${Number(x.match_score).toFixed(1)}%`,
    },
    {
      label: "Official page",
      get: (x) =>
        x.url && !isNil(x.url)
          ? `<a href="${escapeHtml(
              x.url
            )}" target="_blank" rel="noopener">Open</a>`
          : "—",
      isHtml: true,
    },
  ];

  const header = items.map((_, i) => `<th>Option ${i + 1}</th>`).join("");
  const body = rows
    .map((row) => {
      const cols = items
        .map((x) => {
          const v = row.get(x);
          return `<td>${row.isHtml ? v : escapeHtml(String(v))}</td>`;
        })
        .join("");
      return `<tr><th>${escapeHtml(row.label)}</th>${cols}</tr>`;
    })
    .join("");

  elComparePanel.innerHTML = `
    <h2>Comparison</h2>
    <p class="sub" title="Match score is relative similarity within the current search run (not accuracy).">
      Match score is relative similarity within the current search run (not accuracy).
    </p>
    <div class="compareTableWrap">
      <table class="compareTable">
        <thead><tr><th>Field</th>${header}</tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
  elComparePanel.style.display = "block";
}

// --------------------
// Render search results
// --------------------
function renderResults(items, uiMeta = null, noteText = "") {
  if (!elResults) return;
  elResults.innerHTML = renderSearchSummary(uiMeta, noteText);
  lastResults = items || [];
  lastUiMeta = uiMeta || null;
  lastNoteText = noteText || "";

  (items || []).forEach((r) => {
    const key = courseKey(r);
    const isChecked = compareSelected.has(key);

    const skills = fmt(r.skills);
    const duration = fmt(r.duration);
    const fees = fmt(r.fees);
    const prerequisites = fmt(r.prerequisites);
    const entryReq = fmt(r.entry_requirements);

    const card = document.createElement("div");
    card.className = "card";

    const courseId = (r.course_id || "").trim();
    const hasCourseId = !!courseId;
    const isAlreadySaved = hasCourseId && savedIds.has(courseId);

    card.innerHTML = `
      <div class="card-main">
        <div class="card-top">
          <h3>${escapeHtml(r.course_name || "Nil")}</h3>

          <label class="comparePick">
            <input type="checkbox" data-key="${escapeHtml(key)}" ${
      isChecked ? "checked" : ""
    } />
            Compare
          </label>
        </div>

        <div class="meta">${escapeHtml(r.institution || "Nil")} • ${escapeHtml(
      r.institution_type || "Nil"
    )} • ${escapeHtml(r.level || "Nil")}</div>

        ${
          skills
            ? `<div class="skills"><strong>Skills:</strong> ${escapeHtml(
                skills
              )}</div>`
            : ""
        }
        ${
          duration
            ? `<div class="meta"><span class="label">Duration:</span> ${escapeHtml(
                duration
              )}</div>`
            : ""
        }
        ${
          fees
            ? `<div class="meta"><span class="label">Fees:</span> ${escapeHtml(
                fees
              )}</div>`
            : ""
        }
        ${
          prerequisites
            ? `<div class="meta"><span class="label">Prerequisites:</span> ${escapeHtml(
                prerequisites
              )}</div>`
            : ""
        }
        ${
          entryReq
            ? `<div class="meta"><span class="label">Entry requirements:</span> ${escapeHtml(
                entryReq
              )}</div>`
            : ""
        }

        <p>${escapeHtml(r.description || "")}</p>

        ${renderWhyMatched(r)}
        ${renderMissingFields(r)}

        ${
          r.url && !isNil(r.url)
            ? `<a class="officialLink" data-course-id="${escapeHtml(courseId)}"
                 href="${escapeHtml(r.url)}" target="_blank" rel="noopener">
                 Open official page
               </a>`
            : ""
        }

        <div class="actions">
          <button class="btnSave" data-course-id="${escapeHtml(courseId)}"
            ${hasCourseId && !isAlreadySaved ? "" : "disabled"}>
            ${isAlreadySaved ? "Saved" : "Save"}
          </button>

          <button class="btnLike" data-course-id="${escapeHtml(courseId)}" ${
      hasCourseId ? "" : "disabled"
    }>👍</button>

          <button class="btnDislike" data-course-id="${escapeHtml(courseId)}" ${
      hasCourseId ? "" : "disabled"
    }>👎</button>
        </div>
      </div>

      <div class="score">
        <div class="scoreLabel" title="Relative similarity for this search run (not accuracy).">
          Match score ⓘ
        </div>
        <div class="scoreVal">${
          isNil(r.match_score) ? "—" : `${Number(r.match_score).toFixed(1)}%`
        }</div>
      </div>
    `;

    const checkbox = card.querySelector('input[type="checkbox"][data-key]');
    if (checkbox) {
      checkbox.addEventListener("change", (e) => {
        const ok = toggleCompare(r, e.target.checked);
        if (!ok) e.target.checked = false;
      });
    }

    const official = card.querySelector(".officialLink");
    if (official) {
      official.addEventListener("click", () => {
        const cid = official.getAttribute("data-course-id");
        if (cid) logEvent(cid, "click", lastQueryText);
      });
    }

    const saveBtn = card.querySelector(".btnSave");
    if (saveBtn) {
      saveBtn.addEventListener("click", async () => {
        const cid = saveBtn.getAttribute("data-course-id");
        if (!cid) return setMsg("No course_id found for this course.");

        saveBtn.disabled = true;
        const ok = await saveCourse(cid);
        if (ok) {
          saveBtn.textContent = "Saved";
        } else {
          saveBtn.disabled = false;
          saveBtn.textContent = "Save";
        }
      });
    }

    const likeBtn = card.querySelector(".btnLike");
    const dislikeBtn = card.querySelector(".btnDislike");

    if (likeBtn) {
      likeBtn.addEventListener("click", async () => {
        const cid = likeBtn.getAttribute("data-course-id");
        if (!cid) return;

        const comment =
          prompt("Optional: Why did you like this course? (Cancel for none)") ||
          "";
        const ok = await sendFeedback(cid, +1, comment);
        if (ok) setMsg("✅ Feedback saved (Liked).");
      });
    }

    if (dislikeBtn) {
      dislikeBtn.addEventListener("click", async () => {
        const cid = dislikeBtn.getAttribute("data-course-id");
        if (!cid) return;

        const comment =
          prompt(
            "Optional: Why did you dislike this course? (Cancel for none)"
          ) || "";
        const ok = await sendFeedback(cid, -1, comment);
        if (ok) setMsg("✅ Feedback saved (Disliked).");
      });
    }

    elResults.appendChild(card);
  });
}

// --------------------
// Render saved-only view
// --------------------
function renderSaved(items) {
  if (!elSavedPanel) return;

  if (!items || items.length === 0) {
    elSavedPanel.innerHTML = `
      <h2>⭐ Saved Courses</h2>
      <p class="sub">No saved courses yet. Go back and press “Save” on a course.</p>
    `;
    elSavedPanel.style.display = "block";
    return;
  }

  const cards = items
    .map((r) => {
      const skills = fmt(r.skills);
      const duration = fmt(r.duration);
      const fees = fmt(r.fees);
      const prerequisites = fmt(r.prerequisites);
      const entryReq = fmt(r.entry_requirements);

      const cid = (r.course_id || "").trim();

      return `
        <div class="card">
          <div class="card-main">
            <div class="card-top">
              <h3>${escapeHtml(r.course_name || "Nil")}</h3>
            </div>

            <div class="meta">${escapeHtml(
              r.institution || "Nil"
            )} • ${escapeHtml(r.institution_type || "Nil")} • ${escapeHtml(
        r.level || "Nil"
      )}</div>

            ${
              skills
                ? `<div class="skills"><strong>Skills:</strong> ${escapeHtml(
                    skills
                  )}</div>`
                : ""
            }
            ${
              duration
                ? `<div class="meta"><span class="label">Duration:</span> ${escapeHtml(
                    duration
                  )}</div>`
                : ""
            }
            ${
              fees
                ? `<div class="meta"><span class="label">Fees:</span> ${escapeHtml(
                    fees
                  )}</div>`
                : ""
            }
            ${
              prerequisites
                ? `<div class="meta"><span class="label">Prerequisites:</span> ${escapeHtml(
                    prerequisites
                  )}</div>`
                : ""
            }
            ${
              entryReq
                ? `<div class="meta"><span class="label">Entry requirements:</span> ${escapeHtml(
                    entryReq
                  )}</div>`
                : ""
            }

            <p>${escapeHtml(r.description || "")}</p>

            ${renderMissingFields(r)}

            ${
              r.url && !isNil(r.url)
                ? `<a class="officialLinkSaved" data-course-id="${escapeHtml(
                    cid
                  )}" href="${escapeHtml(
                    r.url
                  )}" target="_blank" rel="noopener">
                    Open official page
                  </a>`
                : ""
            }

            <div class="actions">
              <button class="btnRemoveSaved" data-course-id="${escapeHtml(
                cid
              )}">Remove</button>
              <button class="btnLikeSaved" data-course-id="${escapeHtml(
                cid
              )}">👍</button>
              <button class="btnDislikeSaved" data-course-id="${escapeHtml(
                cid
              )}">👎</button>
            </div>
          </div>
        </div>
      `;
    })
    .join("");

  elSavedPanel.innerHTML = `<h2>⭐ Saved Courses</h2>${cards}`;
  elSavedPanel.style.display = "block";

  elSavedPanel.querySelectorAll(".officialLinkSaved").forEach((a) => {
    a.addEventListener("click", () => {
      const cid = a.getAttribute("data-course-id");
      if (cid) logEvent(cid, "click", lastQueryText);
    });
  });

  elSavedPanel.querySelectorAll(".btnRemoveSaved").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const cid = btn.getAttribute("data-course-id");
      if (!cid) return;

      try {
        btn.disabled = true;
        await removeSavedCourse(cid);
        setMsg("✅ Removed from saved.");
        await loadSavedPanel();
        await refreshSavedIds();
      } catch (e) {
        console.error(e);
        btn.disabled = false;
        setMsg("Remove failed.");
      }
    });
  });

  elSavedPanel.querySelectorAll(".btnLikeSaved").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const cid = btn.getAttribute("data-course-id");
      if (!cid) return;
      const comment =
        prompt("Optional: Why did you like this course? (Cancel for none)") ||
        "";
      const ok = await sendFeedback(cid, +1, comment);
      if (ok) setMsg("✅ Feedback saved (Liked).");
    });
  });

  elSavedPanel.querySelectorAll(".btnDislikeSaved").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const cid = btn.getAttribute("data-course-id");
      if (!cid) return;
      const comment =
        prompt(
          "Optional: Why did you dislike this course? (Cancel for none)"
        ) || "";
      const ok = await sendFeedback(cid, -1, comment);
      if (ok) setMsg("✅ Feedback saved (Disliked).");
    });
  });
}

async function loadSavedPanel() {
  setMsg("Loading saved courses...");
  const details = await fetchSavedDetailsForUser();
  const items = details.results || [];

  savedIds = new Set(
    items.map((x) => (x.course_id || "").trim()).filter(Boolean)
  );

  renderSaved(items);
  setMsg("");
}

// --------------------
// Search
// --------------------
async function doSearch() {
  if (!elQuery) return;

  const q = elQuery.value.trim();
  if (!q) return setMsg("Please enter a keyword (e.g., cybersecurity).");

  lastQueryText = q;

  showSearchView();

  setMsg("Searching...");
  if (elResults) elResults.innerHTML = "";
  if (elBtn) elBtn.disabled = true;

  compareSelected.clear();
  updateCompareBar();

  try {
    await refreshSavedIds();
  } catch (e) {
    console.warn("Could not refresh saved IDs:", e);
  }

  const body = {
    query: q,
    user_id: getUserId(),
    institution_type: elType ? elType.value : "All",
    level: elLevel ? elLevel.value : "All",
    institution: elInst ? elInst.value : "All",
    top_k: 10,
    use_semantic: !!(elUseSemantic && elUseSemantic.checked),
    hybrid: !!(elUseHybrid && elUseHybrid.checked),
    requires_math: !!(elRequiresMath && elRequiresMath.checked),
    requires_english: !!(elRequiresEnglish && elRequiresEnglish.checked),
  };

  try {
    const res = await fetch(`${API}/api/search`, {
      method: "POST",
      mode: "cors",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const data = await res.json();

    if (!data.results || data.results.length === 0) {
      setMsg(data.message || "No results. Try different keywords.");
      return;
    }

    setMsg("");
    renderResults(data.results, data.ui_meta || null, data.note || "");
  } catch (err) {
    console.error(err);
    setMsg("Something went wrong contacting the API.");
  } finally {
    if (elBtn) elBtn.disabled = false;
  }
}

// --------------------
// Wire up events
// --------------------
if (elBtn) elBtn.addEventListener("click", doSearch);

if (elQuery) {
  elQuery.addEventListener("keydown", (e) => {
    if (e.key === "Enter") doSearch();
  });
}

if (elBtnSaved) {
  elBtnSaved.addEventListener("click", async () => {
    if (!showingSaved) {
      showSavedView();
      try {
        await loadSavedPanel();
      } catch (e) {
        console.error(e);
        setMsg("Could not load saved courses.");
        renderSaved([]);
      }
    } else {
      showSearchView();
      setMsg("");
      if (lastResults.length)
        renderResults(lastResults, lastUiMeta, lastNoteText);
    }
  });
}

if (elUseSemantic && elUseHybrid) {
  elUseSemantic.addEventListener("change", () => {
    elUseHybrid.disabled = !elUseSemantic.checked;
    if (!elUseSemantic.checked) elUseHybrid.checked = false;
  });
}

if (elBtnCompare) {
  elBtnCompare.addEventListener("click", () => {
    if (!showingSaved) renderComparePanel();
  });
}

if (elBtnClearCompare) {
  elBtnClearCompare.addEventListener("click", () => {
    compareSelected.clear();
    updateCompareBar();
    if (lastResults.length)
      renderResults(lastResults, lastUiMeta, lastNoteText);
  });
}

// --------------------
// Init
// --------------------
(async function init() {
  await loadMeta();
  try {
    await refreshSavedIds();
  } catch {}
  updateCompareBar();
})();
