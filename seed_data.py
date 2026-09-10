"""
Seed sample data: 2 client engagements, each with 2-3 sprints and a mix
of tasks in different states, so the app has something realistic to show
on first run.

Run standalone with: python seed_data.py
Or imported and called via seed() — used by app.py to auto-seed on
Streamlit Cloud, where there's no way to run this script manually since
the deployed filesystem starts empty every time the app spins up fresh.
"""

from datetime import date
import db


def seed():
    db.reset_db()

    # ---- Engagement 1: pharma commercial analytics ----
    eng1 = db.add_engagement(
        client_name="Meridian Pharma",
        engagement_name="Commercial Analytics Platform Rollout",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 8, 15),
    )

    sprint1 = db.add_sprint(eng1, 1, "Data model + segmentation logic", date(2026, 5, 1), date(2026, 5, 15))
    sprint2 = db.add_sprint(eng1, 2, "Rep-facing UI + coverage tracking", date(2026, 5, 15), date(2026, 5, 29))
    sprint3 = db.add_sprint(eng1, 3, "UAT + client sign-off", date(2026, 5, 29), date(2026, 6, 12))

    # Sprint 1 tasks — all done
    t1 = db.add_task(sprint1, "Design HCP segmentation schema", "R. Iyer", 8,
                      ["Peer reviewed", "Matches client data dictionary"])
    t2 = db.add_task(sprint1, "Build scoring SQL views", "R. Iyer", 5,
                      ["Unit tested against sample data", "Peer reviewed"])
    t3 = db.add_task(sprint1, "Validate segmentation against client's manual tiers", "S. Bose", 5,
                      ["Client analyst confirmed match"])
    for t in [t1, t2, t3]:
        db.update_task_status(t, "In Progress")
        db.update_task_status(t, "QA Review")
        for qc in db.get_tasks(sprint1):
            if qc["id"] == t:
                for check in qc["qa_checks"]:
                    db.set_qa_check(check["id"], True, "S. Bose")
        db.update_task_status(t, "Done", date(2026, 5, 13))

    # Sprint 2 tasks — mix of states
    t4 = db.add_task(sprint2, "Build rep coverage dashboard", "R. Iyer", 8,
                      ["Unit tested", "Tested with 3 sample territories"])
    db.update_task_status(t4, "In Progress")
    db.update_task_status(t4, "QA Review")
    qa_t4 = [t for t in db.get_tasks(sprint2) if t["id"] == t4][0]["qa_checks"]
    db.set_qa_check(qa_t4[0]["id"], True, "S. Bose")
    # second check deliberately left unpassed — this task is stuck at the QA gate

    t5 = db.add_task(sprint2, "Add decline-alert flagging", "S. Bose", 5,
                      ["Unit tested", "Peer reviewed"])
    db.update_task_status(t5, "In Progress")

    t6 = db.add_task(sprint2, "Client walkthrough of dashboard v1", "R. Iyer", 3, ["Client feedback logged"])
    # left in Backlog

    # ---- Engagement 2: retail pricing engagement ----
    eng2 = db.add_engagement(
        client_name="Northfield Retail Group",
        engagement_name="Dynamic Pricing Engine — Phase 1",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 9, 1),
    )
    sprint4 = db.add_sprint(eng2, 1, "Requirements + data audit", date(2026, 6, 1), date(2026, 6, 15))
    t7 = db.add_task(sprint4, "Interview category managers", "A. Rao", 3, ["Notes reviewed by PM"])
    db.update_task_status(t7, "In Progress")
    t8 = db.add_task(sprint4, "Audit existing pricing data sources", "A. Rao", 5,
                      ["Data quality report reviewed", "Gaps documented"])
    # left in Backlog

    print("Seeded 2 engagements, 4 sprints, 8 tasks with a realistic mix of statuses and QA gate states.")


if __name__ == "__main__":
    seed()
