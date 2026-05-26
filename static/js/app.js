// Tutorial Center frontend. Talks to its own host.
const API = "";

// --- tiny helpers ---
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
    const d = new Date(s);
    if (isNaN(d.getTime())) return s;
    return d.toLocaleString();
}

// --- tabs ---
function showPage(id) {
    document.querySelectorAll(".page").forEach((p) => p.toggleAttribute("hidden", p.id !== id));
    document.querySelectorAll('nav button[data-page]').forEach((b) => {
        b.setAttribute("aria-selected", b.dataset.page === id ? "true" : "false");
    });
}

document.querySelectorAll('nav button[data-page]').forEach((b) => {
    b.addEventListener("click", () => showPage(b.dataset.page));
});

// arrow-key nav for tabs
document.querySelector("nav").addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
    const tabs = [...document.querySelectorAll('nav button[data-page]')];
    const i = tabs.indexOf(document.activeElement);
    if (i < 0) return;
    const next = tabs[(i + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length];
    next.focus();
    showPage(next.dataset.page);
});

// --- health badge ---
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

// --- student data ---
let currentLessons = {};
let currentSummary = {};

async function fetchStudentData() {
    const id = parseInt($("studentIdInput").value, 10);
    const info = $("studentInfo");
    const tabs = $("courseTabs");
    const details = $("lessonDetails");
    const csvLink = $("csvExportLink");
    info.innerHTML = ""; tabs.innerHTML = ""; details.innerHTML = ""; csvLink.classList.add("hidden");
    if (!id || id <= 0) { $("studentIdInput").classList.add("invalid"); return toast("Enter a student ID", "warn"); }
    $("studentIdInput").classList.remove("invalid");

    try {
        const data = await withLoading($("fetchStudentBtn"), () => api("/student_data", { method: "POST", body: { student_id: id } }));
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

        csvLink.href = `/students/${id}/lessons.csv`;
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

$("fetchStudentBtn").addEventListener("click", fetchStudentData);
$("studentIdInput").addEventListener("keydown", (e) => { if (e.key === "Enter") fetchStudentData(); });

// --- add student ---
$("addStudentForm").addEventListener("submit", async (e) => {
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
    } catch (err) {
        toast(err.message, "error");
    }
});

// --- course search (debounced) ---
const searchCourses = debounce(async () => {
    const q = $("courseSearchInput").value.trim();
    const out = $("courseResults");
    out.innerHTML = "";
    if (q.length < 2) return;
    try {
        const courses = await api(`/search_courses?course_name_partial=${encodeURIComponent(q)}`);
        if (!courses.length) {
            out.append(el("p", { class: "empty-state" }, "No matching courses."));
            return;
        }
        courses.forEach((c) => {
            const card = el("div", { class: "course-card" },
                el("strong", {}, `${c.course_name}  ·  course #${c.course_id}`),
                el("p", {}, "Upcoming start times: " + (c.available_start_times.join(", ") || "—")),
            );
            const btn = el("button", { type: "button" }, "Select");
            btn.addEventListener("click", () => selectCourse(c));
            card.append(btn);
            out.append(card);
        });
    } catch (e) {
        toast(e.message, "error");
    }
}, 300);

function selectCourse(c) {
    $("selectedCourseId").value = c.course_id;
    $("selectedCourseName").textContent = c.course_name;
    const sel = $("startTime");
    sel.innerHTML = "";
    (c.available_start_times.length ? c.available_start_times : ["09:00"]).forEach((t) => {
        sel.append(el("option", { value: t }, t));
    });
    $("registrationForm").hidden = false;
    $("registrationForm").scrollIntoView({ behavior: "smooth" });
}

$("courseSearchInput").addEventListener("input", searchCourses);

$("registerBtn").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    const body = {
        student_id: parseInt($("registrationStudentId").value, 10),
        course_id: parseInt($("selectedCourseId").value, 10),
        day_of_week: $("dayOfWeek").value,
        start_time: $("startTime").value,
        number_of_lessons: parseInt($("numberOfLessons").value, 10),
        first_lesson_date: $("firstLessonDate").value || null,
    };
    if (!body.student_id || !body.course_id || !body.number_of_lessons) {
        return toast("Fill in student ID, course, and # of lessons", "warn");
    }
    try {
        const r = await withLoading(btn, () => api("/register_lessons", { method: "POST", body }));
        toast(`Registered ${r.registered_lessons_count} lesson(s).`, "success");
        $("registrationForm").hidden = true;
        $("courseResults").innerHTML = "";
        $("courseSearchInput").value = "";
    } catch (e) {
        toast(e.message, "error");
    }
});

// --- attendance ---
$("fetchParticipantsBtn").addEventListener("click", async (e) => {
    const lessonId = parseInt($("attendanceLessonId").value, 10);
    if (!lessonId) return toast("Enter a lesson ID", "warn");
    const list = $("participantsList");
    list.innerHTML = "";
    $("attendanceForm").hidden = true;
    try {
        const participants = await withLoading(e.currentTarget, () => api(`/lesson_participants?lesson_id=${lessonId}`));
        if (!participants.length) {
            list.append(el("p", { class: "empty-state" }, "No participants registered."));
            return;
        }
        participants.forEach((p) => {
            list.append(el("label", {},
                el("input", { type: "checkbox", value: p.student_id, name: "student" }),
                ` ${p.name} (ID: ${p.student_id})`,
            ));
        });
        $("attendanceForm").hidden = false;
    } catch (err) {
        toast(err.message, "error");
    }
});

$("attendanceForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const lessonId = parseInt($("attendanceLessonId").value, 10);
    const ids = [...e.currentTarget.querySelectorAll('input[name="student"]:checked')].map((c) => parseInt(c.value, 10));
    if (!ids.length) return toast("Select at least one student", "warn");
    const btn = e.currentTarget.querySelector("button[type=submit]");
    try {
        const r = await withLoading(btn, () => api("/mark_attendance_bulk", {
            method: "POST",
            body: { lesson_id: lessonId, student_ids: ids },
        }));
        $("attendanceResult").innerHTML = "";
        $("attendanceResult").append(
            el("p", {}, `Marked ${r.marked_count} attended.`),
        );
        if (r.errors && r.errors.length) {
            const ul = el("ul");
            r.errors.forEach((err) => ul.append(el("li", {}, `Student ${err.student_id}: ${err.detail}`)));
            $("attendanceResult").append(ul);
            toast(`${r.errors.length} failures`, "warn");
        } else {
            toast(`Attendance marked for ${r.marked_count} student(s)`, "success");
        }
    } catch (err) {
        toast(err.message, "error");
    }
});

// --- calendar ---
async function runCalendar(path, btn) {
    const months = parseInt($("monthsAhead").value, 10);
    if (!months || months < 1) return toast("Enter months ahead (≥1)", "warn");
    try {
        const r = await withLoading(btn, () => api(path, { method: "POST", body: { months_ahead: months } }));
        $("calendarResult").innerHTML = "";
        $("calendarResult").append(el("p", {}, r.message));
        if (r.events && r.events.length) {
            const ul = el("ul");
            r.events.forEach((ev) => ul.append(el("li", {}, `${ev.summary} — ${fmtDate(ev.start)}`)));
            $("calendarResult").append(ul);
        }
        toast(r.message, "success");
    } catch (e) {
        toast(e.message, "error");
    }
}

$("syncCalendarBtn").addEventListener("click", (e) => runCalendar("/sync_calendar_events", e.currentTarget));
$("regenerateCalendarBtn").addEventListener("click", (e) => {
    if (!confirm("This deletes ALL events in the calendar within the window and recreates them. Continue?")) return;
    runCalendar("/generate_calendar_events", e.currentTarget);
});

// init
refreshHealth();
