import streamlit as st
import streamlit.components.v1 as components
import pdfplumber
import re
import time
import os
import requests
import shutil
import io
import base64
# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcq_paper_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

DOWNLOAD_TIMEOUT = 15  # seconds per attempt


# --------------------------------------------------
# PDF RENDERING
# --------------------------------------------------
def display_pdf(pdf_path=None, pdf_bytes=None):
    if pdf_bytes is None:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

    base64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")

    pdf_display = f"""
        <iframe
            src="data:application/pdf;base64,{base64_pdf}"
            width="100%"
            height="1000px"
            type="application/pdf">
        </iframe>
    """

    st.markdown(pdf_display, unsafe_allow_html=True)


def render_live_clock(start_time):
    initial_elapsed = int(time.time() - start_time)
    components.html(
        f"""
        <div id="live-clock" style="
            text-align: center;
            background: #0d1117;
            border: 1px solid #1f2937;
            border-radius: 10px;
            padding: 0.55rem 0.7rem;
            color: #e2e8f0;
            font-weight: 700;
            font-family: sans-serif;
        ">TIME 00:00</div>
        <script>
            const baseElapsed = {initial_elapsed};
            const mountedAt = Date.now();
            const el = document.getElementById("live-clock");
            const pad = (n) => String(n).padStart(2, "0");
            const tick = () => {{
                const elapsed = baseElapsed + Math.floor((Date.now() - mountedAt) / 1000);
                const m = Math.floor(elapsed / 60);
                const s = elapsed % 60;
                el.textContent = `TIME ${{pad(m)}}:${{pad(s)}}`;
            }};
            tick();
            setInterval(tick, 1000);
        </script>
        """,
        height=66,
    )


def enable_keyboard_option_shortcuts():
    components.html(
        """
        <script>
            const keyMap = {
                "a": "A", "b": "B", "c": "C", "d": "D",
                "1": "A", "2": "B", "3": "C", "4": "D"
            };

            const isTypingTarget = (el) => {
                if (!el) return false;
                const tag = (el.tagName || "").toLowerCase();
                return tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable;
            };

            const clickOption = (label) => {
                const doc = window.parent.document;

                // Current answer controls are segmented controls; click matching option.
                const segCandidates = Array.from(
                    doc.querySelectorAll('div[data-testid="stSegmentedControl"] label, div[data-testid="stSegmentedControl"] button')
                );
                for (const el of segCandidates) {
                    const txt = (el.innerText || "").trim();
                    if (txt === label) {
                        el.click();
                        return true;
                    }
                }

                // Fallback: any visible button labeled A/B/C/D.
                const buttons = Array.from(doc.querySelectorAll("button"));
                for (const btn of buttons) {
                    const txt = (btn.innerText || "").trim();
                    if (txt === label) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            };

            const clickNav = (label) => {
                const buttons = Array.from(window.parent.document.querySelectorAll("button"));
                for (const btn of buttons) {
                    const txt = (btn.innerText || "").trim().toLowerCase();
                    if (txt === label.toLowerCase()) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            };

            if (!window.parent.__mcqShortcutsBound) {
                window.parent.addEventListener("keydown", (e) => {
                    if (e.repeat) return;
                    if (isTypingTarget(e.target)) return;
                    if (e.ctrlKey || e.metaKey || e.altKey) return;

                    const mapped = keyMap[(e.key || "").toLowerCase()];
                    let clicked = false;

                    if (mapped) {
                        clicked = clickOption(mapped);
                    } else if (e.key === "ArrowLeft") {
                        clicked = clickNav("Prev");
                    } else if (e.key === "ArrowRight" || e.key === "Enter") {
                        clicked = clickNav("Next");
                    }

                    if (clicked) {
                        e.preventDefault();
                    }
                });
                window.parent.__mcqShortcutsBound = true;
            }
        </script>
        """,
        height=0,
    )


# --------------------------------------------------
# SUBJECT DATA
# --------------------------------------------------
SUBJECTS_IGCSE = {
    "0580": "Mathematics",
    "0625": "Physics",
    "0620": "Chemistry",
    "0610": "Biology",
    "0450": "Business Studies",
    "0455": "Economics",
    "0478": "Computer Science",
    "0500": "English First Language",
    "0510": "English Second Language",
    "0470": "History",
    "0460": "Geography",
    "0452": "Accounting",
}

SUBJECTS_ALEVEL = {
    "9702": "Physics",
    "9701": "Chemistry",
    "9700": "Biology",
    "9709": "Mathematics",
    "9231": "Further Mathematics",
    "9708": "Economics",
    "9609": "Business",
    "9618": "Computer Science",
    "9093": "English Language",
    "9695": "English Literature",
    "9489": "History",
    "9696": "Geography",
    "9706": "Accounting",
}

SUBJECT_URL_NAMES = {
    # IGCSE
    "0580": "Mathematics%20(0580)",
    "0625": "Physics%20(0625)",
    "0620": "Chemistry%20(0620)",
    "0610": "Biology%20(0610)",
    "0450": "Business%20Studies%20(0450)",
    "0455": "Economics%20(0455)",
    "0478": "Computer%20Science%20(0478)",
    "0500": "English%20-%20First%20Language%20(0500)",
    "0510": "English%20-%20Second%20Language%20(0510)",
    "0470": "History%20(0470)",
    "0460": "Geography%20(0460)",
    "0452": "Accounting%20(0452)",
    # A Level
    "9702": "Physics%20(9702)",
    "9701": "Chemistry%20(9701)",
    "9700": "Biology%20(9700)",
    "9709": "Mathematics%20(9709)",
    "9231": "Further%20Mathematics%20(9231)",
    "9708": "Economics%20(9708)",
    "9609": "Business%20(9609)",
    "9618": "Computer%20Science%20(9618)",
    "9093": "English%20Language%20(9093)",
    "9695": "English%20Literature%20(9695)",
    "9489": "History%20(9489)",
    "9696": "Geography%20(9696)",
    "9706": "Accounting%20(9706)",
}


def get_download_urls(subject_code, year, session, component, level, paper_type):
    """Generate candidate download URLs for a given paper."""
    year_short = str(year)[-2:]
    level_url = "Cambridge%20IGCSE" if level == "igcse" else "A%20Levels"
    subject_url = SUBJECT_URL_NAMES.get(subject_code, f"Unknown%20({subject_code})")
    filename = f"{subject_code}_{session}{year_short}_{paper_type}_{component}.pdf"
    return [
        f"https://papers.gceguide.xyz/{level_url}/{subject_url}/{year}/{filename}",
        f"https://papers.gceguide.com/{level_url}/{subject_url}/{year}/{filename}",
        f"https://pastpapers.papacambridge.com/directories/CAIE/CAIE-pastpapers/upload/{filename}",
    ]


def download_pdf(subject_code, year, session, component, level, paper_type):
    """Download a PDF (if not cached) and return its local path. Returns None on failure."""
    year_short = str(year)[-2:]
    filename = f"{subject_code}_{session}{year_short}_{paper_type}_{component}.pdf"
    local_path = os.path.join(CACHE_DIR, filename)

    if os.path.exists(local_path):
        return local_path, True  # (path, was_cached)

    urls = get_download_urls(subject_code, year, session, component, level, paper_type)
    for url in urls:
        try:
            r = requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True)
            if r.status_code == 200 and "pdf" in r.headers.get("Content-Type", "").lower():
                with open(local_path, "wb") as f:
                    shutil.copyfileobj(r.raw, f)
                return local_path, False
        except Exception:
            continue

    return None, False


# --------------------------------------------------
# MARK SCHEME PARSER
# --------------------------------------------------
def extract_answers_from_markscheme(pdf_source):
    """Extract MCQ answers (Q->A/B/C/D) from a mark scheme PDF."""
    answers = {}
    try:
        with pdfplumber.open(pdf_source) as pdf:
            full_text = ""
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    full_text += t + "\n"

        pattern = r"(\d+)\s+([A-D])\b"
        for q, ans in re.findall(pattern, full_text):
            q_num = int(q)
            if 1 <= q_num <= 100:
                answers[q_num] = ans

        if not answers:
            pattern2 = r"^\s*(\d{1,2})\s+([A-D])\s*$"
            for q, ans in re.findall(pattern2, full_text, re.MULTILINE):
                q_num = int(q)
                if 1 <= q_num <= 100:
                    answers[q_num] = ans
    except Exception as e:
        st.warning(f"Could not parse mark scheme: {e}")
    return answers


# --------------------------------------------------
# APP CONFIG
# --------------------------------------------------
st.set_page_config(page_title="Cambridge MCQ Practice", layout="wide", page_icon="📘")

st.markdown(
    """
<style>
    .stApp { background: #07090c; }
    .big-title { font-size: 2rem; font-weight: 800; color: #e2e8f0; }
    .sub { color: #94a3b8; font-size: 0.9rem; }
    .answer-btn button {
        width: 100%; border-radius: 8px; font-weight: 700; font-size: 1.1rem;
    }
    div[data-testid="stSidebar"] { background: #0d1117; }

    button[kind="primary"] {
        background-color: #1c5413 !important;
        border: 1px solid #2b7a1f !important;
        color: #f0fdf4 !important;
    }
    button[kind="primary"]:hover {
        background-color: #236a19 !important;
        border: 1px solid #319126 !important;
    }
    button[kind="primary"]:active {
        background-color: #18490f !important;
    }

    div[data-testid="stSegmentedControl"] [role="radiogroup"],
    div[data-testid="stSegmentedControl"] [data-baseweb="button-group"] {
        gap: 0.45rem;
    }
    div[data-testid="stSegmentedControl"] input[type="radio"] {
        accent-color: #3b82f6 !important;
    }
    div[data-testid="stSegmentedControl"] label:has(input[type="radio"]:checked) {
        border-color: #3b82f6 !important;
        background: #1e3a8a !important;
        color: #dbeafe !important;
        box-shadow: inset 0 0 0 1px #60a5fa !important;
    }
    div[data-testid="stSegmentedControl"] label:has(input[type="radio"]:checked) * {
        color: #dbeafe !important;
    }
    div[data-testid="stSegmentedControl"] [role="radio"],
    div[data-testid="stSegmentedControl"] button,
    div[data-testid="stSegmentedControl"] [data-baseweb="button-group"] button {
        min-height: 46px !important;
        padding: 0.6rem 1rem !important;
        border-radius: 10px !important;
        border: 1px solid #334155 !important;
        background: #0d1117 !important;
        color: #e2e8f0 !important;
        font-weight: 700 !important;
    }
    div[data-testid="stSegmentedControl"] [role="radio"][aria-checked="true"],
    div[data-testid="stSegmentedControl"] button[aria-pressed="true"],
    div[data-testid="stSegmentedControl"] button[data-selected="true"],
    div[data-testid="stSegmentedControl"] [data-baseweb="button-group"] button[aria-pressed="true"],
    div[data-testid="stSegmentedControl"] [data-baseweb="button-group"] button[data-selected="true"] {
        border-color: #3b82f6 !important;
        background: #1e3a8a !important;
        color: #dbeafe !important;
        box-shadow: inset 0 0 0 1px #60a5fa !important;
    }
    div[data-testid="stSegmentedControl"] [data-baseweb="button-group"] button[aria-pressed="true"] * {
        color: #dbeafe !important;
    }
</style>
""",
    unsafe_allow_html=True,
)


# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------
defaults = {
    "answers": {},
    "correct_answers": {},
    "question_number": 1,
    "start_time": time.time(),
    "exam_finished": False,
    "qp_path": None,
    "qp_bytes": None,
    "ms_path": None,
    "paper_details": "No paper loaded",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# --------------------------------------------------
# SIDEBAR - PAPER SELECTOR
# --------------------------------------------------
with st.sidebar:
    st.markdown("## Paper Selector")
    st.caption("Auto-downloads from GCE Guide")

    level = st.selectbox("Level", ["A Level", "IGCSE"])
    level_key = "alevel" if level == "A Level" else "igcse"

    subjects = SUBJECTS_ALEVEL if level_key == "alevel" else SUBJECTS_IGCSE
    subject_display = {f"{name} ({code})": code for code, name in sorted(subjects.items(), key=lambda x: x[1])}
    chosen_display = st.selectbox("Subject", list(subject_display.keys()))
    subject_code = subject_display[chosen_display]

    year = st.selectbox("Year", list(range(2025, 2014, -1)))
    session = st.selectbox("Session", ["May/June (s)", "Oct/Nov (w)", "Feb/Mar (m)"])
    session_key = {"May/June (s)": "s", "Oct/Nov (w)": "w", "Feb/Mar (m)": "m"}[session]

    component = st.selectbox("Component", ["11", "12", "13", "21", "22", "31", "32", "41", "42", "43"])

    st.divider()

    if st.button("Load Paper", width=500, type="primary"):
        with st.spinner("Downloading question paper..."):
            qp_path, qp_cached = download_pdf(subject_code, year, session_key, component, level_key, "qp")
        with st.spinner("Downloading mark scheme..."):
            ms_path, ms_cached = download_pdf(subject_code, year, session_key, component, level_key, "ms")

        if qp_path:
            st.session_state.qp_path = qp_path
            st.session_state.qp_bytes = None
            st.session_state.paper_details = (
                f"{level} | {chosen_display} | {year} | {session} | Component {component}"
            )
            msg = "Loaded from cache" if qp_cached else "Downloaded successfully"
            st.success(msg)
        else:
            st.error("Could not find the question paper. Try a different component or year.")

        if ms_path:
            st.session_state.ms_path = ms_path
            st.session_state.correct_answers = extract_answers_from_markscheme(ms_path)
            n = len(st.session_state.correct_answers)
            if n > 0:
                st.success(f"Mark scheme loaded ({n} answers)")
            else:
                st.warning("Mark scheme downloaded but no answers parsed.")
        else:
            st.warning("Mark scheme not available - feedback disabled.")

        st.session_state.answers = {}
        st.session_state.question_number = 1
        st.session_state.start_time = time.time()
        st.session_state.exam_finished = False

    st.divider()
    with st.expander("Or upload manually"):
        manual_qp = st.file_uploader("Question Paper PDF", type="pdf", key="manual_qp")
        manual_ms = st.file_uploader("Mark Scheme PDF", type="pdf", key="manual_ms")

        if st.button("Load Uploaded Files"):
            if manual_qp:
                qp_bytes = manual_qp.read()
                st.session_state.qp_bytes = qp_bytes
                st.session_state.qp_path = None
                st.session_state.paper_details = "Manual upload | Question Paper PDF"
                st.success("Question paper loaded")
            if manual_ms:
                st.session_state.correct_answers = extract_answers_from_markscheme(io.BytesIO(manual_ms.read()))
                st.session_state.ms_path = "manual"
                st.success(f"Mark scheme loaded ({len(st.session_state.correct_answers)} answers)")
            st.session_state.answers = {}
            st.session_state.question_number = 1
            st.session_state.start_time = time.time()
            st.session_state.exam_finished = False


# --------------------------------------------------
# MAIN AREA
# --------------------------------------------------
if not st.session_state.qp_path and not st.session_state.qp_bytes:
    st.markdown('<div class="big-title">Cambridge MCQ Practice</div>', unsafe_allow_html=True)
    st.info("Select a paper from the sidebar and click Load Paper to begin.")
    st.info("Created by: Dharshan Balu\nCo-Creators: Adhvik Sunil")
    st.warning(
        "This app is still under development! Selecting anything other than MCQ components will cause errors. "
        "For the full user manual, visit the GitHub file."
    )
    st.stop()

elapsed = int(time.time() - st.session_state.start_time)

title_col, clock_col = st.columns([3, 1])
with title_col:
    st.markdown('<div class="big-title">Cambridge MCQ Practice</div>', unsafe_allow_html=True)
with clock_col:
    render_live_clock(st.session_state.start_time)

st.caption(
    f"Paper: {st.session_state.paper_details} | "
    f"Question: {st.session_state.question_number} | "
    f"Mark scheme: {'loaded' if st.session_state.correct_answers else 'not loaded'}"
)

mode = st.radio("Mode:", ["Practice (Instant Feedback)", "Exam (No Feedback)"], horizontal=True)
st.divider()
enable_keyboard_option_shortcuts()

col_pdf, col_answer = st.columns([2, 1])

# PDF viewer
with col_pdf:
    if st.session_state.qp_bytes:
        display_pdf(pdf_bytes=st.session_state.qp_bytes)
    else:
        display_pdf(pdf_path=st.session_state.qp_path)

# Answer panel
with col_answer:
    q = st.session_state.question_number
    is_practice = mode.startswith("Practice")

    if st.session_state.exam_finished:
        st.subheader("Results")
        score = 0
        incorrect = []
        for qn, user_ans in st.session_state.answers.items():
            correct_ans = st.session_state.correct_answers.get(qn)
            if correct_ans:
                if user_ans == correct_ans:
                    score += 1
                else:
                    incorrect.append((qn, user_ans, correct_ans))

        total_marked = len([qn for qn in st.session_state.answers if qn in st.session_state.correct_answers])

        if total_marked > 0:
            pct = round(score / total_marked * 100)
            color = "#22c55e" if pct >= 70 else "#f59e0b" if pct >= 50 else "#ef4444"
            st.markdown(f"### <span style='color:{color}'>{score}/{total_marked} ({pct}%)</span>", unsafe_allow_html=True)
        else:
            st.write(f"Score: {score}/{len(st.session_state.answers)} answered")
            st.warning("No mark scheme loaded - cannot calculate percentage.")

        if incorrect:
            st.subheader("Mistakes")
            for qn, ua, ca in sorted(incorrect):
                st.write(f"**Q{qn}**: You chose **{ua}** -> Correct: **{ca}**")
        elif score > 0:
            st.success("Perfect score")

        if st.button("Restart", width=500):
            st.session_state.answers = {}
            st.session_state.question_number = 1
            st.session_state.start_time = time.time()
            st.session_state.exam_finished = False
            st.rerun()

    else:
        st.subheader(f"Question {q}")

        prev_answer = st.session_state.answers.get(q)

        def select_answer(option):
            st.session_state.answers[q] = option
            st.session_state["_feedback"] = None

        def render_practice_option(option):
            selected = st.session_state.answers.get(q)
            correct = st.session_state.correct_answers.get(q)
            bg = "#0d1117"
            border = "#334155"
            text = "#e2e8f0"

            if selected == option:
                if correct:
                    if selected == correct:
                        bg, border, text = "#14532d", "#22c55e", "#dcfce7"
                    else:
                        bg, border, text = "#7f1d1d", "#ef4444", "#fee2e2"
                else:
                    bg, border, text = "#1e3a8a", "#3b82f6", "#dbeafe"
            elif selected and correct and option == correct:
                bg, border, text = "#14532d", "#22c55e", "#dcfce7"

            st.markdown(
                f"""
                <div style="
                    width: 100%;
                    min-height: 46px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    text-align: center;
                    padding: 0.6rem 1rem;
                    border-radius: 10px;
                    border: 1px solid {border};
                    background: {bg};
                    color: {text};
                    font-weight: 700;
                    font-size: 1rem;
                ">{option}</div>
                """,
                unsafe_allow_html=True,
            )

        if is_practice:
            if prev_answer:
                pcolA, pcolB, pcolC, pcolD = st.columns(4)
                with pcolA:
                    render_practice_option("A")
                with pcolB:
                    render_practice_option("B")
                with pcolC:
                    render_practice_option("C")
                with pcolD:
                    render_practice_option("D")
            else:
                practice_key = f"practice_choice_q{q}"
                practice_choice = st.segmented_control(
                    "Practice Answer",
                    ["A", "B", "C", "D"],
                    default=None,
                    key=practice_key,
                    label_visibility="collapsed",
                    width="stretch",
                )
                if practice_choice:
                    select_answer(practice_choice)
                    st.rerun()
        else:
            exam_key = f"exam_choice_q{q}"
            choice = st.segmented_control(
                "Exam Answer",
                ["A", "B", "C", "D"],
                default=prev_answer if prev_answer in ["A", "B", "C", "D"] else None,
                key=exam_key,
                label_visibility="collapsed",
                width="stretch",
            )
            if choice and st.session_state.answers.get(q) != choice:
                st.session_state.answers[q] = choice

        st.divider()

        nav_col1, nav_col2 = st.columns(2)
        with nav_col1:
            if q > 1 and st.button("Prev", width=500):
                st.session_state.question_number -= 1
                st.session_state["_feedback"] = None
                st.rerun()
        with nav_col2:
            if st.button("Next", width=500):
                if q not in st.session_state.answers:
                    st.warning("Please answer before moving on.")
                else:
                    st.session_state.question_number += 1
                    st.session_state["_feedback"] = None
                    st.rerun()

        st.divider()
        answered = len(st.session_state.answers)
        st.caption(f"Answered: {answered} question(s)")

        progress = answered / 40 if answered <= 40 else 1.0
        st.progress(progress)

        if st.button("Finish Exam", width=500, type="primary"):
            st.session_state.exam_finished = True
            st.rerun()
