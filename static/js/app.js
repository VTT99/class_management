// Tutorial Center frontend. Three runtime configurations are supported:
//   1. Integrated:    served by FastAPI at "/" (data-root-path injected into script tag).
//   2. Sub-path:      served by FastAPI behind a reverse proxy (data-root-path = "/class_management").
//   3. Split-deploy:  static files on a different origin than the API. A small
//                     config.js loaded before this script sets window.API_BASE
//                     (e.g. "https://api.example.com") and optionally
//                     window.API_TOKEN for bearer auth.
const API =
    (typeof window !== "undefined" && window.API_BASE) ||
    document.querySelector("script[data-root-path]")?.dataset.rootPath ||
    "";
const API_TOKEN = (typeof window !== "undefined" && window.API_TOKEN) || "";

// --- helpers ---
const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, ...children) => {
    const node = document.createElement(tag);
    Object.entries(props).forEach(([k, v]) => {
        if (k === "class") node.className = v;
        else if (k === "dataset") Object.assign(node.dataset, v);
        else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
        else if (v !== undefined && v !== null) node.setAttribute(k, v);
    });
    children.flat().forEach((c) => node.append(c instanceof Node ? c : document.createTextNode(String(c))));
    return node;
};

function toast(message, kind = "info") {
    const t = el("div", { class: `toast ${kind}` }, message);
    $("toast-stack").append(t);
    setTimeout(() => t.remove(), 4000);
}

async function api(path, { method = "GET", body } = {}) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body);
    }
    if (API_TOKEN) opts.headers["Authorization"] = `Bearer ${API_TOKEN}`;
    const res = await fetch(API + path, opts);
    if (!res.ok) {
        let detail = res.statusText;
        try {
            const data = await res.json();
            detail = (typeof data.detail === "object")
                ? (data.detail.message || JSON.stringify(data.detail))
                : (data.detail || detail);
        } catch (_) {}
        throw new Error(detail);
    }
    if (res.headers.get("content-type")?.includes("application/json")) return res.json();
    return res.text();
}

async function withLoading(btn, fn) {
    btn.classList.add("is-loading");
    btn.disabled = true;
    try { return await fn(); }
    finally { btn.classList.remove("is-loading"); btn.disabled = false; }
}

function debounce(fn, ms) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

function fmtDate(s) {
    if (!s) return "";
    const d = new Date(s.replace(" ", "T"));
    if (isNaN(d.getTime())) return s;
    return d.toLocaleString();
}

function fmtTime(s) {
    if (!s) return "";
    const d = new Date(s.replace(" ", "T"));
    if (isNaN(d.getTime())) return s;
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function isoDate(d) {
    return d.toISOString().slice(0, 10);
}

// === Tabs ===========================================================
function showPage(id) {
    document.querySelectorAll(".page").forEach((p) => p.toggleAttribute("hidden", p.id !== id));
    document.querySelectorAll('nav button[data-page]').forEach((b) => {
        b.setAttribute("aria-selected", b.dataset.page === id ? "true" : "false");
    });
    if (id === "calendarPage") renderCalendar();
}

document.querySelectorAll('nav button[data-page]').forEach((b) => {
    b.addEventListener("click", () => showPage(b.dataset.page));
});

document.querySelector("nav").addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
    const tabs = [...document.querySelectorAll('nav button[data-page]')];
    const i = tabs.indexOf(document.activeElement);
    if (i < 0) return;
    const next = tabs[(i + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length];
    next.focus();
    showPage(next.dataset.page);
});

// === Health badge ===================================================
async function refreshHealth() {
    const badge = $("health-badge");
    try {
        const data = await api("/health");
        badge.textContent = data.status === "ok" ? "API ok" : `API ${data.status}`;
        badge.className = "badge " + (data.status === "ok" ? "badge-ok" : "badge-err");
        badge.title = `db: ${data.db}\ncalendar configured: ${data.calendar_configured}`;
    } catch (e) {
        badge.textContent = "API down";
        badge.className = "badge badge-err";
        badge.title = e.message;
    }
}

// === Student tab ====================================================
let currentLessons = {};
let currentSummary = {};

async function fetchStudentData(studentId) {
    const id = parseInt(studentId, 10);
    const info = $("studentInfo");
    const tabs = $("courseTabs");
    const details = $("lessonDetails");
    const csvLink = $("csvExportLink");
    info.innerHTML = ""; tabs.innerHTML = ""; details.innerHTML = ""; csvLink.classList.add("hidden");
    if (!id || id <= 0) { return toast("Enter a student ID or name", "warn"); }

    try {
        const data = await api("/student_data", { method: "POST", body: { student_id: id } });
        const s = data.student;
        info.append(
            el("h3", {}, s.name),
            el("p", {}, `ID: ${s.student_id} · ${s.gender} · Parent: ${s.parent_contact}`),
            el("p", {}, `Payment: ${s.payment_method} · Registered: ${s.date_of_register} · Referee: ${s.referee || "—"}`),
        );

        currentSummary = data.course_summary || {};
        currentLessons = data.lessons || {};
        const courseIds = Object.keys(currentSummary);
        if (!courseIds.length) {
            details.append(el("p", { class: "empty-state" }, "No course registrations for this student."));
        } else {
            courseIds.forEach((cid, idx) => {
                const c = currentSummary[cid];
                const btn = el("button", { type: "button", dataset: { courseId: cid }, "aria-pressed": idx === 0 ? "true" : "false" },
                    `${c.course_name} (${c.completed}/${c.total})`);
                btn.addEventListener("click", () => renderCourseLessons(cid));
                tabs.append(btn);
            });
            renderCourseLessons(courseIds[0]);
        }

        csvLink.onclick = (e) => { e.preventDefault(); downloadCsv(id); };
        csvLink.classList.remove("hidden");
    } catch (e) {
        toast(e.message, "error");
    }
}

function renderCourseLessons(courseId) {
    const details = $("lessonDetails");
    details.innerHTML = "";
    document.querySelectorAll('#courseTabs button').forEach((b) => {
        b.setAttribute("aria-pressed", b.dataset.courseId === String(courseId) ? "true" : "false");
    });
    const summary = currentSummary[courseId];
    const lessons = currentLessons[courseId] || [];

    details.append(el("h4", {}, `${summary.course_name} — ${summary.completed} done, ${summary.uncomplete} missed, ${summary.not_yet_complete} upcoming`));

    if (!lessons.length) {
        details.append(el("p", { class: "empty-state" }, "No lessons recorded."));
        return;
    }

    const table = el("table");
    table.append(
        el("thead", {}, el("tr", {},
            el("th", {}, "Lesson"), el("th", {}, "Start"),
            el("th", {}, "End"), el("th", {}, "Status"),
        )),
    );
    const tbody = el("tbody");
    lessons.forEach((l) => {
        tbody.append(el("tr", {},
            el("td", { "data-label": "Lesson" }, l.lesson_id),
            el("td", { "data-label": "Start" }, fmtDate(l.start_datetime)),
            el("td", { "data-label": "End" }, fmtDate(l.end_datetime)),
            el("td", { "data-label": "Status", class: "status-" + (l.lesson_status || "").replace(/[^a-z-]/g, "") }, l.lesson_status),
        ));
    });
    table.append(tbody);
    details.append(table);
}

async function downloadCsv(studentId) {
    try {
        const headers = {};
        if (API_TOKEN) headers["Authorization"] = `Bearer ${API_TOKEN}`;
        const res = await fetch(`${API}/students/${studentId}/lessons.csv`, { headers });
        if (!res.ok) throw new Error("CSV export failed: " + res.status);
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `student_${studentId}_lessons.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (e) {
        toast(e.message, "error");
    }
}

// --- student search (debounced) ---
const searchStudents = debounce(async () => {
    const q = $("studentSearchInput").value.trim();
    const out = $("studentSearchResults");
    out.innerHTML = "";
    if (q.length < 1) return;
    try {
        const matches = await api(`/search_students?q=${encodeURIComponent(q)}`);
        if (!matches.length) {
            out.append(el("p", { class: "empty-state" }, "No matching students."));
            return;
        }
        matches.forEach((m) => {
            const row = el("div", { class: "student-card" });
            const btn = el("button", { type: "button" }, `#${m.student_id} — ${m.name}`);
            btn.addEventListener("click", () => {
                $("studentSearchResults").innerHTML = "";
                fetchStudentData(m.student_id);
            });
            row.append(btn);
            out.append(row);
        });
    } catch (e) {
        toast(e.message, "error");
    }
}, 300);

$("studentSearchInput").addEventListener("input", searchStudents);
$("studentSearchInput").addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const v = $("studentSearchInput").value.trim();
    if (/^\d+$/.test(v)) {
        $("studentSearchResults").innerHTML = "";
        fetchStudentData(v);
    } else {
        searchStudents();
    }
});

// --- Add Student modal ---
$("openAddStudentBtn").addEventListener("click", () => $("addStudentDialog").showModal());

$("addStudentForm").addEventListener("submit", async (e) => {
    // Prevent the dialog's default "close" submit so we can show errors.
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    const body = Object.fromEntries(fd.entries());
    if (!body.referee) body.referee = null;
    const btn = form.querySelector("button[type=submit]");
    try {
        const result = await withLoading(btn, () => api("/add_student", { method: "POST", body }));
        toast(`Added student #${result.student_id}`, "success");
        form.reset();
        $("addStudentDialog").close();
    } catch (err) {
        toast(err.message, "error");
    }
});

// === Calendar tab ===================================================
let calendarView = "week"; // "week" or "month"
let calendarAnchor = startOfDay(new Date()); // For week: start of view (Mon-aligned). For month: any day in shown month.

function startOfDay(d) {
    const x = new Date(d);
    x.setHours(0, 0, 0, 0);
    return x;
}
function addDays(d, n) {
    const x = new Date(d);
    x.setDate(x.getDate() + n);
    return x;
}
function startOfWeek(d) {
    // Monday-start (UK convention). 0=Sun..6=Sat. Adjust to 1=Mon..7=Sun.
    const x = startOfDay(d);
    const dow = (x.getDay() + 6) % 7; // 0=Mon..6=Sun
    x.setDate(x.getDate() - dow);
    return x;
}
function startOfMonth(d) {
    const x = new Date(d.getFullYear(), d.getMonth(), 1);
    x.setHours(0, 0, 0, 0);
    return x;
}
function endOfMonth(d) {
    const x = new Date(d.getFullYear(), d.getMonth() + 1, 0);
    x.setHours(23, 59, 59, 0);
    return x;
}

async function renderCalendar() {
    if (calendarView === "week") return renderWeek();
    return renderMonth();
}

async function renderWeek() {
    const grid = $("calendarWeekGrid");
    const monthGrid = $("calendarMonthGrid");
    grid.hidden = false;
    monthGrid.hidden = true;
    grid.innerHTML = "";

    // Anchor the week on the user's currently-shown range
    // (calendarAnchor stays the same when navigating prev/next).
    const start = startOfWeek(calendarAnchor);
    const end = addDays(start, 6);
    $("calendarRangeLabel").textContent =
        `${start.toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${end.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`;

    // Build header row
    grid.append(el("div", { class: "week-grid-corner" }));
    const today = isoDate(startOfDay(new Date()));
    const dayDates = [];
    for (let i = 0; i < 7; i++) {
        const day = addDays(start, i);
        dayDates.push(day);
        const isToday = isoDate(day) === today;
        grid.append(el("div", {
            class: "week-grid-day-header" + (isToday ? " is-today" : ""),
            style: `grid-column: ${i + 2};`,
        }, day.toLocaleDateString(undefined, { weekday: "short", day: "numeric" })));
    }

    // Build time column + grid cells (rows for 8..21 inclusive => 14 rows).
    const HOUR_START = 8, HOUR_END = 21;
    for (let h = HOUR_START; h <= HOUR_END; h++) {
        const row = h - HOUR_START + 2; // +1 for header, +1 because grid is 1-indexed
        grid.append(el("div", { class: "week-grid-time", style: `grid-row: ${row};` },
            `${String(h).padStart(2, "0")}:00`));
        for (let i = 0; i < 7; i++) {
            const isToday = isoDate(dayDates[i]) === today;
            grid.append(el("div", {
                class: "week-grid-cell" + (isToday ? " is-today" : ""),
                style: `grid-row: ${row}; grid-column: ${i + 2};`,
                dataset: { day: isoDate(dayDates[i]), hour: h },
            }));
        }
    }

    // Fetch + place lessons
    let lessons = [];
    try {
        lessons = await api(`/lessons?start_date=${isoDate(start)}&end_date=${isoDate(end)}`);
    } catch (e) {
        toast(`Failed to load calendar: ${e.message}`, "error");
        return;
    }
    lessons.forEach((l) => placeLessonInWeek(grid, l));
}

function placeLessonInWeek(grid, lesson) {
    const dt = new Date((lesson.start_datetime || "").replace(" ", "T"));
    if (isNaN(dt.getTime())) return;
    const dayIso = isoDate(dt);
    let hour = dt.getHours();
    if (hour < 8) hour = 8;
    if (hour > 21) hour = 21;
    const cell = grid.querySelector(`.week-grid-cell[data-day="${dayIso}"][data-hour="${hour}"]`);
    if (!cell) return;
    const pill = el("button", { type: "button", class: "lesson-pill", title: `Lesson #${lesson.lesson_id}` });
    pill.append(
        el("span", { class: "lesson-pill-time" }, `${fmtTime(lesson.start_datetime)}–${fmtTime(lesson.end_datetime)}`),
        el("span", { class: "lesson-pill-name" }, lesson.course_name),
    );
    pill.addEventListener("click", () => openLessonDialog(lesson));
    cell.append(pill);
}

async function renderMonth() {
    const weekGrid = $("calendarWeekGrid");
    const monthGrid = $("calendarMonthGrid");
    weekGrid.hidden = true;
    monthGrid.hidden = false;
    monthGrid.innerHTML = "";

    const monthStart = startOfMonth(calendarAnchor);
    const monthEnd = endOfMonth(calendarAnchor);
    $("calendarRangeLabel").textContent =
        monthStart.toLocaleDateString(undefined, { month: "long", year: "numeric" });

    // Header
    const header = el("div", { class: "month-grid-header" });
    ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].forEach((d) => header.append(el("div", {}, d)));
    monthGrid.append(header);

    // Build 6-row × 7-col body starting from the Monday on/before monthStart.
    const gridStart = startOfWeek(monthStart);
    const gridEnd = addDays(gridStart, 41); // 6 weeks
    const body = el("div", { class: "month-grid-body" });
    const cellByDay = new Map();
    const today = isoDate(startOfDay(new Date()));
    for (let i = 0; i < 42; i++) {
        const day = addDays(gridStart, i);
        const key = isoDate(day);
        const isOther = day.getMonth() !== monthStart.getMonth();
        const isToday = key === today;
        const cell = el("div", {
            class: "month-day"
                + (isOther ? " is-other-month" : "")
                + (isToday ? " is-today" : ""),
        });
        cell.append(el("span", { class: "month-day-number" }, day.getDate()));
        cellByDay.set(key, cell);
        body.append(cell);
    }
    monthGrid.append(body);

    let lessons = [];
    try {
        lessons = await api(`/lessons?start_date=${isoDate(gridStart)}&end_date=${isoDate(gridEnd)}`);
    } catch (e) {
        toast(`Failed to load calendar: ${e.message}`, "error");
        return;
    }

    // Group by day
    const lessonsByDay = new Map();
    lessons.forEach((l) => {
        const k = (l.start_datetime || "").slice(0, 10);
        if (!lessonsByDay.has(k)) lessonsByDay.set(k, []);
        lessonsByDay.get(k).push(l);
    });

    lessonsByDay.forEach((items, key) => {
        const cell = cellByDay.get(key);
        if (!cell) return;
        const MAX_SHOWN = 3;
        items.slice(0, MAX_SHOWN).forEach((l) => {
            const pill = el("button", { type: "button", class: "lesson-pill", title: `Lesson #${l.lesson_id}` });
            pill.append(
                el("span", { class: "lesson-pill-time" }, fmtTime(l.start_datetime)),
                el("span", { class: "lesson-pill-name" }, l.course_name),
            );
            pill.addEventListener("click", () => openLessonDialog(l));
            cell.append(pill);
        });
        if (items.length > MAX_SHOWN) {
            const more = el("button", { type: "button", class: "month-day-more" },
                `+${items.length - MAX_SHOWN} more`);
            more.addEventListener("click", () => {
                // Switch to week view focused on this date
                calendarAnchor = new Date(key + "T00:00:00");
                setCalendarView("week");
            });
            cell.append(more);
        }
    });
}

function setCalendarView(view) {
    calendarView = view;
    document.querySelectorAll(".view-toggle button[data-view]").forEach((b) => {
        b.classList.toggle("active", b.dataset.view === view);
    });
    renderCalendar();
}

document.querySelectorAll(".view-toggle button[data-view]").forEach((b) => {
    b.addEventListener("click", () => setCalendarView(b.dataset.view));
});

$("calendarPrevBtn").addEventListener("click", () => {
    if (calendarView === "week") calendarAnchor = addDays(calendarAnchor, -7);
    else calendarAnchor = startOfMonth(new Date(calendarAnchor.getFullYear(), calendarAnchor.getMonth() - 1, 1));
    renderCalendar();
});
$("calendarNextBtn").addEventListener("click", () => {
    if (calendarView === "week") calendarAnchor = addDays(calendarAnchor, 7);
    else calendarAnchor = startOfMonth(new Date(calendarAnchor.getFullYear(), calendarAnchor.getMonth() + 1, 1));
    renderCalendar();
});
$("calendarTodayBtn").addEventListener("click", () => {
    calendarAnchor = startOfDay(new Date());
    renderCalendar();
});

// --- Lesson dialog ---
let currentLesson = null;

async function openLessonDialog(lesson) {
    currentLesson = lesson;
    $("lessonDialogTitle").textContent = `${lesson.course_name} — Lesson #${lesson.lesson_id}`;
    $("lessonDialogSubtitle").textContent = `${fmtDate(lesson.start_datetime)} → ${fmtDate(lesson.end_datetime)}`;
    $("lessonAddStudentInput").value = "";
    $("lessonAddStudentResults").innerHTML = "";
    await refreshLessonParticipants(lesson.lesson_id);
    $("lessonDialog").showModal();
}

async function refreshLessonParticipants(lessonId) {
    const wrap = $("lessonParticipants");
    wrap.innerHTML = "";
    let participants = [];
    try {
        participants = await api(`/lesson_participants?lesson_id=${lessonId}`);
    } catch (e) {
        if (e.message.includes("No participants")) {
            wrap.append(el("p", { class: "empty-state" }, "No students registered yet."));
            return;
        }
        toast(e.message, "error");
        return;
    }
    participants.forEach((p) => {
        const lab = el("label", {});
        lab.append(
            el("input", { type: "checkbox", value: p.student_id, name: "student" }),
            ` ${p.name} (#${p.student_id})`,
        );
        wrap.append(lab);
    });
}

$("markAllAttendedBtn").addEventListener("click", async (e) => {
    if (!currentLesson) return;
    const ids = [...$("lessonParticipants").querySelectorAll('input[name="student"]:checked')]
        .map((c) => parseInt(c.value, 10));
    const pushAbsent = $("pushAbsentCheck").checked;
    if (!ids.length && !pushAbsent) {
        return toast("Select at least one student, or enable push-absent", "warn");
    }
    try {
        const r = await withLoading(e.currentTarget, () => api("/mark_attendance_bulk", {
            method: "POST",
            body: {
                lesson_id: currentLesson.lesson_id,
                student_ids: ids,
                push_absent: pushAbsent,
            },
        }));
        const errs = r.errors?.length || 0;
        const pushedN = r.pushed_count || 0;
        let msg = `Marked ${r.marked_count} attended`;
        if (pushedN) msg += `, pushed ${pushedN} absent`;
        if (errs) msg += `, ${errs} failed`;
        toast(msg, errs ? "warn" : "success");

        // Highlight attended students.
        $("lessonParticipants").querySelectorAll("label").forEach((lab) => {
            const cb = lab.querySelector('input');
            if (cb && cb.checked) lab.classList.add("is-attended");
        });

        // Show the pushed report below the button.
        const report = $("pushedReport");
        report.innerHTML = "";
        if (r.pushed?.length || r.pushed_failed?.length) {
            report.hidden = false;
            if (r.pushed?.length) {
                report.append(el("h4", {}, `Pushed to next class:`));
                const ul = el("ul");
                r.pushed.forEach((p) => ul.append(el("li", {},
                    `${p.student_name} (#${p.student_id}) → lesson #${p.to_lesson_id} on ${fmtDate(p.to_start_datetime)}`)));
                report.append(ul);
            }
            if (r.pushed_failed?.length) {
                report.append(el("h4", {}, `Could not push:`));
                const ul = el("ul");
                r.pushed_failed.forEach((p) => ul.append(el("li", {},
                    `${p.student_name} (#${p.student_id}): ${p.reason}`)));
                report.append(ul);
            }
        } else {
            report.hidden = true;
        }
    } catch (err) {
        toast(err.message, "error");
    }
});

const searchStudentsForLesson = debounce(async () => {
    const q = $("lessonAddStudentInput").value.trim();
    const out = $("lessonAddStudentResults");
    out.innerHTML = "";
    if (q.length < 1) return;
    try {
        const matches = await api(`/search_students?q=${encodeURIComponent(q)}`);
        if (!matches.length) {
            out.append(el("p", { class: "empty-state" }, "No matching students."));
            return;
        }
        matches.forEach((m) => {
            const row = el("div", { class: "student-card" });
            const btn = el("button", { type: "button" }, `#${m.student_id} — ${m.name}  ·  Add`);
            btn.addEventListener("click", async () => {
                btn.disabled = true;
                try {
                    await api("/add_lesson_registration", {
                        method: "POST",
                        body: { student_id: m.student_id, lesson_id: currentLesson.lesson_id },
                    });
                    toast(`Added ${m.name} to this class`, "success");
                    $("lessonAddStudentInput").value = "";
                    out.innerHTML = "";
                    await refreshLessonParticipants(currentLesson.lesson_id);
                } catch (err) {
                    btn.disabled = false;
                    toast(err.message, "error");
                }
            });
            row.append(btn);
            out.append(row);
        });
    } catch (e) {
        toast(e.message, "error");
    }
}, 300);

$("lessonAddStudentInput").addEventListener("input", searchStudentsForLesson);

// --- Add Class modal (single / weekly-N-days / daily) ---
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

async function populateCourseSelect() {
    const sel = $("addClassCourseSelect");
    sel.innerHTML = "";
    try {
        const courses = await api("/courses");
        const active = courses.filter((c) => c.active);
        const list = active.length ? active : courses;
        list.forEach((c) => sel.append(el("option", { value: c.course_id }, c.course_name)));
    } catch (e) {
        toast(`Couldn't load courses: ${e.message}`, "error");
    }
}

function addWeeklyDayRow(initial = {}) {
    const wrap = $("addClassDaysList");
    const row = el("div", { class: "day-row form-row", style: "gap:6px; flex-wrap:nowrap;" });
    const daySel = el("select", { class: "day-row-day" });
    WEEKDAYS.forEach((d) => daySel.append(el("option", { value: d }, d)));
    if (initial.day) daySel.value = initial.day;
    const startIn = el("input", { type: "time", class: "day-row-start", value: initial.start || "10:00", style: "max-width:110px;" });
    const endIn = el("input", { type: "time", class: "day-row-end", value: initial.end || "11:00", style: "max-width:110px;" });
    const rmBtn = el("button", { type: "button", class: "btn-secondary", title: "Remove" }, "×");
    rmBtn.addEventListener("click", () => { row.remove(); refreshPreview(); });
    [daySel, startIn, endIn].forEach((i) => i.addEventListener("change", refreshPreview));
    row.append(daySel, startIn, endIn, rmBtn);
    wrap.append(row);
    refreshPreview();
}

function setAddClassType(type) {
    const simple = $("addClassSimpleFields");
    const weekly = $("addClassWeeklyFields");
    const durRow = $("addClassDurationRow");
    const unit = $("addClassDurationUnit");

    if (type === "single") {
        simple.hidden = false; weekly.hidden = true; durRow.hidden = true;
    } else if (type === "daily") {
        simple.hidden = false; weekly.hidden = true; durRow.hidden = false;
        unit.textContent = "days";
    } else { // weekly
        simple.hidden = true; weekly.hidden = false; durRow.hidden = false;
        unit.textContent = "weeks";
        if (!$("addClassDaysList").children.length) addWeeklyDayRow();
    }
    refreshPreview();
}

function collectWeeklyDays() {
    return [...document.querySelectorAll("#addClassDaysList .day-row")].map((r) => ({
        day: r.querySelector(".day-row-day").value,
        start: r.querySelector(".day-row-start").value,
        end: r.querySelector(".day-row-end").value,
    }));
}

function computeLessonsFromForm() {
    const courseId = parseInt($("addClassCourseSelect").value, 10);
    if (!courseId) return { error: "Pick a course" };
    const type = $("addClassType").value;
    const out = [];

    if (type === "single") {
        const d = $("addClassDate").value, s = $("addClassStart").value, e = $("addClassEnd").value;
        if (!d || !s || !e) return { error: "Fill in date and times" };
        out.push({ course_id: courseId, start_datetime: `${d} ${s}:00`, end_datetime: `${d} ${e}:00` });
    } else if (type === "daily") {
        const d = $("addClassDate").value, s = $("addClassStart").value, e = $("addClassEnd").value;
        const n = parseInt($("addClassDuration").value, 10);
        if (!d || !s || !e || !n) return { error: "Fill in date, times and # of days" };
        const base = new Date(d + "T00:00:00");
        for (let i = 0; i < n; i++) {
            const day = isoDate(addDays(base, i));
            out.push({ course_id: courseId, start_datetime: `${day} ${s}:00`, end_datetime: `${day} ${e}:00` });
        }
    } else { // weekly
        const weekStart = $("addClassWeekStart").value;
        const weeks = parseInt($("addClassDuration").value, 10);
        if (!weekStart || !weeks) return { error: "Pick a start week and # of weeks" };
        const days = collectWeeklyDays();
        if (!days.length) return { error: "Add at least one day-of-week" };
        for (const d of days) {
            if (!d.start || !d.end) return { error: "Every weekly row needs a start and end time" };
        }
        const monday = startOfWeek(new Date(weekStart + "T00:00:00"));
        for (let w = 0; w < weeks; w++) {
            for (const occ of days) {
                const idx = WEEKDAYS.indexOf(occ.day);
                const day = isoDate(addDays(monday, w * 7 + idx));
                out.push({
                    course_id: courseId,
                    start_datetime: `${day} ${occ.start}:00`,
                    end_datetime: `${day} ${occ.end}:00`,
                });
            }
        }
    }
    return { lessons: out };
}

function refreshPreview() {
    const r = computeLessonsFromForm();
    const p = $("addClassPreview");
    if (r.error) { p.textContent = r.error; return; }
    p.textContent = `Will create ${r.lessons.length} lesson(s).`;
}

$("addClassType").addEventListener("change", (e) => setAddClassType(e.currentTarget.value));
["addClassCourseSelect", "addClassDate", "addClassStart", "addClassEnd", "addClassDuration", "addClassWeekStart"]
    .forEach((id) => $(id).addEventListener("input", refreshPreview));

$("addClassAddDayBtn").addEventListener("click", () => addWeeklyDayRow());

$("openAddClassBtn").addEventListener("click", async () => {
    await populateCourseSelect();
    const todayStr = isoDate(new Date());
    $("addClassDate").value = todayStr;
    $("addClassWeekStart").value = todayStr;
    $("addClassStart").value = "09:00";
    $("addClassEnd").value = "10:00";
    $("addClassDuration").value = 6;
    $("addClassType").value = "single";
    $("addClassDaysList").innerHTML = "";
    setAddClassType("single");
    $("addClassDialog").showModal();
});

$("addClassForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const r = computeLessonsFromForm();
    if (r.error) return toast(r.error, "warn");
    const btn = e.currentTarget.querySelector("button[type=submit]");
    try {
        const res = await withLoading(btn, () => api("/add_lessons_bulk", {
            method: "POST", body: { lessons: r.lessons },
        }));
        toast(`Created ${res.lessons.length} lesson(s).`, "success");
        $("addClassDialog").close();
        renderCalendar();
    } catch (err) {
        toast(err.message, "error");
    }
});

// --- Sync Google Calendar ---
$("syncCalendarBtn").addEventListener("click", async (e) => {
    if (!confirm("Sync the next 1 month of lessons to Google Calendar?")) return;
    try {
        const r = await withLoading(e.currentTarget, () => api("/sync_calendar_events", {
            method: "POST",
            body: { months_ahead: 1 },
        }));
        toast(r.message, "success");
    } catch (err) {
        toast(err.message, "error");
    }
});

// --- Upload DB → Google Sheets ---
$("uploadSheetsBtn").addEventListener("click", async (e) => {
    if (!confirm("Overwrite every worksheet in your Google Sheet with the current DB contents?")) return;
    try {
        const r = await withLoading(e.currentTarget, () => api("/upload_db_to_sheets", { method: "POST" }));
        const pushed = (r.pushed || []).map((p) => `${p.table} (${p.rows} rows)`).join(", ");
        toast(`Uploaded: ${pushed || "nothing"}`, "success");
        if (r.skipped?.length) {
            console.warn("Skipped tables:", r.skipped);
            toast(`${r.skipped.length} table(s) skipped — see console`, "warn");
        }
    } catch (err) {
        toast(err.message, "error");
    }
});

// --- Generic modal close handler (any button with data-close-modal) ---
document.querySelectorAll("[data-close-modal]").forEach((btn) => {
    btn.addEventListener("click", () => btn.closest("dialog")?.close());
});

// === init ===========================================================
refreshHealth();
