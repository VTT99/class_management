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
let calendarStart = startOfDay(new Date());

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

async function renderCalendar() {
    const grid = $("calendarGrid");
    grid.innerHTML = "";
    const start = startOfDay(calendarStart);
    const end = addDays(start, 6);
    $("calendarRangeLabel").textContent =
        `${start.toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${end.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`;

    let lessons = [];
    try {
        lessons = await api(`/lessons?start_date=${isoDate(start)}&end_date=${isoDate(end)}`);
    } catch (e) {
        toast(`Failed to load calendar: ${e.message}`, "error");
        return;
    }

    const byDay = new Map();
    for (let i = 0; i < 7; i++) {
        byDay.set(isoDate(addDays(start, i)), []);
    }
    lessons.forEach((l) => {
        const day = (l.start_datetime || "").slice(0, 10);
        if (byDay.has(day)) byDay.get(day).push(l);
    });

    const today = isoDate(startOfDay(new Date()));
    for (let i = 0; i < 7; i++) {
        const day = addDays(start, i);
        const key = isoDate(day);
        const isToday = key === today;
        const col = el("div", { class: "calendar-day" + (isToday ? " is-today" : "") });
        col.append(el("div", { class: "calendar-day-header" },
            day.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })));

        const body = el("div", { class: "calendar-day-body" });
        const lessonsToday = byDay.get(key) || [];
        if (!lessonsToday.length) {
            body.append(el("p", { class: "empty-state", style: "font-size:12px;margin:0;" }, "—"));
        } else {
            lessonsToday.forEach((l) => {
                const pill = el("button", { type: "button", class: "lesson-pill", title: `Lesson #${l.lesson_id}` });
                pill.append(
                    el("span", { class: "lesson-pill-time" }, `${fmtTime(l.start_datetime)}–${fmtTime(l.end_datetime)}`),
                    el("span", { class: "lesson-pill-name" }, l.course_name),
                );
                pill.addEventListener("click", () => openLessonDialog(l));
                body.append(pill);
            });
        }
        col.append(body);
        grid.append(col);
    }
}

$("calendarPrevBtn").addEventListener("click", () => {
    calendarStart = addDays(calendarStart, -7);
    renderCalendar();
});
$("calendarNextBtn").addEventListener("click", () => {
    calendarStart = addDays(calendarStart, 7);
    renderCalendar();
});
$("calendarTodayBtn").addEventListener("click", () => {
    calendarStart = startOfDay(new Date());
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
    if (!ids.length) return toast("Select at least one student", "warn");
    try {
        const r = await withLoading(e.currentTarget, () => api("/mark_attendance_bulk", {
            method: "POST",
            body: { lesson_id: currentLesson.lesson_id, student_ids: ids },
        }));
        const errs = r.errors?.length || 0;
        toast(`Marked ${r.marked_count} attended${errs ? `, ${errs} failed` : ""}`,
            errs ? "warn" : "success");
        $("lessonParticipants").querySelectorAll("label").forEach((lab) => {
            const cb = lab.querySelector('input');
            if (cb && cb.checked) lab.classList.add("is-attended");
        });
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

// --- Add Class modal ---
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

$("openAddClassBtn").addEventListener("click", async () => {
    await populateCourseSelect();
    $("addClassDate").value = isoDate(new Date());
    $("addClassStart").value = "09:00";
    $("addClassEnd").value = "10:00";
    $("addClassDialog").showModal();
});

$("addClassForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const courseId = parseInt($("addClassCourseSelect").value, 10);
    const day = $("addClassDate").value;
    const start = $("addClassStart").value;
    const end = $("addClassEnd").value;
    if (!courseId || !day || !start || !end) return toast("Fill in all fields", "warn");

    const body = {
        course_id: courseId,
        start_datetime: `${day} ${start}:00`,
        end_datetime: `${day} ${end}:00`,
    };
    const btn = e.currentTarget.querySelector("button[type=submit]");
    try {
        const r = await withLoading(btn, () => api("/add_lesson", { method: "POST", body }));
        toast(`Created lesson #${r.lesson_id}`, "success");
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

// --- Generic modal close handler (any button with data-close-modal) ---
document.querySelectorAll("[data-close-modal]").forEach((btn) => {
    btn.addEventListener("click", () => btn.closest("dialog")?.close());
});

// === init ===========================================================
refreshHealth();
