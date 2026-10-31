const $ = (id) => document.getElementById(id);
const fields = ["name", "email", "course", "semester"];
let searchTimer = null;

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  let body = null;
  try { body = await res.json(); } catch (_) { /* no JSON body */ }
  if (!res.ok) {
    const err = new Error((body && body.error) || "Request failed.");
    err.errors = (body && body.errors) || {};
    throw err;
  }
  return body;
}

function toast(message, bad = false) {
  const t = $("toast");
  t.textContent = message;
  t.className = "show" + (bad ? " bad" : "");
  setTimeout(() => { t.className = ""; }, 2600);
}

function cell(text, cls) {
  const td = document.createElement("td");
  td.textContent = text;
  if (cls) td.className = cls;
  return td;
}

function renderRows(students) {
  const body = $("rows");
  body.replaceChildren();
  $("empty").hidden = students.length > 0;
  for (const s of students) {
    const tr = document.createElement("tr");
    tr.append(cell(s.id), cell(s.name), cell(s.email), cell(s.course), cell(s.semester),
              cell(new Date(s.created_at).toLocaleDateString()));
    const act = document.createElement("td");
    act.className = "act";
    const edit = document.createElement("button");
    edit.className = "small ghost"; edit.textContent = "Edit";
    edit.onclick = () => startEdit(s);
    const del = document.createElement("button");
    del.className = "small danger"; del.textContent = "Delete";
    del.onclick = () => removeStudent(s);
    act.append(edit, del);
    tr.append(act);
    body.append(tr);
  }
}

async function loadStudents() {
  const q = $("search").value.trim();
  try {
    renderRows(await api("/api/students" + (q ? "?q=" + encodeURIComponent(q) : "")));
  } catch (e) { toast(e.message, true); }
}

async function loadStats() {
  try {
    const s = await api("/api/stats");
    $("stat-total").textContent = s.total;
    $("stat-courses").textContent = s.course_count;
    $("stat-avg").textContent = s.average_semester;
    const top = $("stat-top");
    top.replaceChildren();
    if (!s.by_course.length) top.textContent = "No data yet";
    for (const c of s.by_course) {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = `${c.course} (${c.count})`;
      top.append(chip);
    }
  } catch (e) { toast(e.message, true); }
}

function clearErrors() {
  fields.forEach((f) => { $("err-" + f).textContent = ""; $(f).classList.remove("invalid"); });
  $("form-error").textContent = "";
}

function resetForm() {
  $("student-form").reset();
  $("student-id").value = "";
  $("form-title").textContent = "Add a student";
  $("save-btn").textContent = "Add student";
  $("cancel-btn").hidden = true;
  clearErrors();
}

function startEdit(s) {
  clearErrors();
  $("student-id").value = s.id;
  fields.forEach((f) => { $(f).value = s[f]; });
  $("form-title").textContent = `Edit student #${s.id}`;
  $("save-btn").textContent = "Save changes";
  $("cancel-btn").hidden = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
  $("name").focus();
}

async function removeStudent(s) {
  if (!confirm(`Delete ${s.name}? This cannot be undone.`)) return;
  try {
    await api(`/api/students/${s.id}`, { method: "DELETE" });
    toast("Student deleted.");
    if ($("student-id").value === String(s.id)) resetForm();
    refresh();
  } catch (e) { toast(e.message, true); }
}

$("student-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  clearErrors();
  const id = $("student-id").value;
  const payload = Object.fromEntries(fields.map((f) => [f, $(f).value]));
  try {
    await api(id ? `/api/students/${id}` : "/api/students", {
      method: id ? "PUT" : "POST", body: JSON.stringify(payload),
    });
    toast(id ? "Student updated." : "Student added.");
    resetForm();
    refresh();
  } catch (e) {
    let shown = false;
    for (const [field, msg] of Object.entries(e.errors)) {
      if ($("err-" + field)) { $("err-" + field).textContent = msg; $(field).classList.add("invalid"); shown = true; }
    }
    if (!shown) $("form-error").textContent = e.message;
  }
});

$("cancel-btn").addEventListener("click", resetForm);
$("search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadStudents, 250);
});

function refresh() { loadStudents(); loadStats(); }
refresh();
