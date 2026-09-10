import streamlit as st
from datetime import date, datetime
import pandas as pd

import db
from core.models import Task, TaskStatus, QACheck, Sprint
from core.rules import (
    transition_task, can_transition, qa_gate_summary,
    sprint_burndown, sprint_completed_points, velocity,
)

st.set_page_config(page_title="Engagement Delivery Tracker", layout="wide")

db.init_db()

st.title("Engagement Delivery Tracker")
st.caption(
    "Agile delivery tracker for client engagements — sprint boards, burndown, and an "
    "embedded QA gate that structurally blocks marking work Done until every QA check passes. "
    "Business logic in core/rules.py is unit tested (20 tests) and run on every push via GitHub Actions."
)

with st.expander("Design notes"):
    st.markdown(
        "- **Why SQLite, not Postgres:** this project's purpose is CI/testing discipline. "
        "A CI pipeline shouldn't depend on a live external database — SQLite keeps the test "
        "suite fast and dependency-free. See [README](https://github.com/Dhayalramesh/delivery-tracker) for the full reasoning.\n"
        "- **Why the QA gate is enforced in code, not just process:** `core/rules.py` raises "
        "`ValueError` if you try to mark a task Done without every QA check passed — it's "
        "impossible to bypass from the UI, not just discouraged.\n"
        "- [Business logic (unit tested)](https://github.com/Dhayalramesh/delivery-tracker/blob/main/core/rules.py)\n"
        "- [Test suite](https://github.com/Dhayalramesh/delivery-tracker/blob/main/tests/test_rules.py)\n"
        "- [CI workflow](https://github.com/Dhayalramesh/delivery-tracker/blob/main/.github/workflows/ci.yml)"
    )

engagements = db.get_engagements()
if not engagements:
    # Auto-seed on first load. SQLite is a local file excluded from git
    # (see .gitignore), so a freshly deployed instance — like on Streamlit
    # Cloud — always starts with an empty database. There's no way to run
    # seed_data.py manually on a deployed container, so the app seeds
    # itself silently the first time it finds no data. Works identically
    # locally and when deployed.
    import seed_data
    seed_data.seed()
    engagements = db.get_engagements()

eng_options = {f"{e['client_name']} — {e['engagement_name']}": e["id"] for e in engagements}
sel_eng_label = st.selectbox("Engagement", list(eng_options.keys()))
eng_id = eng_options[sel_eng_label]

sprints = db.get_sprints(engagement_id=eng_id)
if not sprints:
    st.info("No sprints for this engagement yet.")
    st.stop()

tab1, tab2, tab3 = st.tabs(["Sprint Board", "Burndown", "Velocity"])

# ---------------- Sprint Board ----------------
with tab1:
    sprint_options = {f"Sprint {s['sprint_number']}: {s['goal']}": s["id"] for s in sprints}
    sel_sprint_label = st.selectbox("Sprint", list(sprint_options.keys()))
    sprint_id = sprint_options[sel_sprint_label]

    tasks_raw = db.get_tasks(sprint_id=sprint_id)

    cols = st.columns(4)
    statuses = ["Backlog", "In Progress", "QA Review", "Done"]
    for col, status in zip(cols, statuses):
        with col:
            st.markdown(f"**{status}**")
            status_tasks = [t for t in tasks_raw if t["status"] == status]
            if not status_tasks:
                st.caption("— empty —")
            for t in status_tasks:
                with st.container(border=True):
                    st.markdown(f"**{t['title']}**")
                    st.caption(f"{t['owner']} · {t['story_points']} pts")
                    if t["qa_checks"]:
                        passed = sum(1 for q in t["qa_checks"] if q["passed"])
                        total = len(t["qa_checks"])
                        st.progress(passed / total if total else 0, text=f"QA: {passed}/{total}")
                        with st.popover("QA checklist"):
                            for q in t["qa_checks"]:
                                new_val = st.checkbox(
                                    q["name"], value=bool(q["passed"]), key=f"qa_{q['id']}"
                                )
                                if new_val != bool(q["passed"]):
                                    db.set_qa_check(q["id"], new_val, "Current user")
                                    st.rerun()

                    # status transition control
                    task_obj = Task(
                        id=t["id"], sprint_id=t["sprint_id"], title=t["title"],
                        owner=t["owner"], story_points=t["story_points"],
                        status=TaskStatus(t["status"]),
                        qa_checks=[QACheck(q["name"], bool(q["passed"])) for q in t["qa_checks"]],
                    )
                    possible_next = [s for s in TaskStatus if can_transition(task_obj.status, s)]
                    if possible_next:
                        next_choice = st.selectbox(
                            "Move to", ["—"] + [s.value for s in possible_next],
                            key=f"move_{t['id']}", label_visibility="collapsed",
                        )
                        if next_choice != "—":
                            try:
                                result = transition_task(task_obj, TaskStatus(next_choice), today=date.today())
                                db.update_task_status(t["id"], result.status.value, result.completed_date)
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))

# ---------------- Burndown ----------------
with tab2:
    sprint_row = next(s for s in sprints if s["id"] == sprint_id)
    tasks_raw = db.get_tasks(sprint_id=sprint_id)

    sprint_obj = Sprint(
        id=sprint_row["id"], engagement_id=sprint_row["engagement_id"],
        sprint_number=sprint_row["sprint_number"], goal=sprint_row["goal"],
        start_date=datetime.strptime(sprint_row["start_date"], "%Y-%m-%d").date(),
        end_date=datetime.strptime(sprint_row["end_date"], "%Y-%m-%d").date(),
    )
    task_objs = [
        Task(
            id=t["id"], sprint_id=t["sprint_id"], title=t["title"], owner=t["owner"],
            story_points=t["story_points"], status=TaskStatus(t["status"]),
            qa_checks=[], 
            completed_date=datetime.strptime(t["completed_date"], "%Y-%m-%d").date() if t["completed_date"] else None,
        )
        for t in tasks_raw
    ]

    burndown = sprint_burndown(sprint_obj, task_objs, today=date.today())
    chart_df = pd.DataFrame({
        "Day": burndown["days"],
        "Ideal": burndown["ideal_remaining"],
        "Actual": burndown["actual_remaining"],
    }).set_index("Day")
    st.subheader(f"Burndown — Sprint {sprint_row['sprint_number']}")
    st.line_chart(chart_df)
    st.caption(f"Total sprint points: {burndown['total_points']}")

# ---------------- Velocity ----------------
with tab3:
    st.subheader("Velocity across completed sprints")
    points_per_sprint = []
    labels = []
    for s in sprints:
        s_tasks = db.get_tasks(sprint_id=s["id"])
        task_objs_v = [Task(
            id=t["id"], sprint_id=t["sprint_id"], title=t["title"], owner=t["owner"],
            story_points=t["story_points"], status=TaskStatus(t["status"]),
        ) for t in s_tasks]
        pts = sprint_completed_points(task_objs_v)
        points_per_sprint.append(pts)
        labels.append(f"Sprint {s['sprint_number']}")

    if points_per_sprint:
        st.bar_chart(pd.DataFrame({"Completed points": points_per_sprint}, index=labels))
        st.metric("Average velocity", f"{velocity(points_per_sprint)} pts/sprint")
