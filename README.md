# Engagement Delivery Tracker

![CI](https://github.com/Dhayalramesh/delivery-tracker/actions/workflows/ci.yml/badge.svg)

An agile delivery tracker for consulting client engagements — sprint boards, burndown charts, velocity tracking, and an **embedded QA gate enforced in code**, not just process: a task cannot be marked Done until every QA check on it has passed. Built to demonstrate SDLC discipline — a real unit-tested business logic layer, and a CI pipeline that runs the full test suite on every push.

**Live demo:** https://delivery-tracker-ke9tzysa9k5tfdtpgidigp.streamlit.app/

## Why this project exists

Most portfolio projects show a UI and a database. This one is built to demonstrate something a client-delivery role actually needs: **agile process discipline that's enforced structurally, not just documented**. The QA gate isn't a checklist item in a wiki somewhere — it's a `ValueError` raised in code if you try to bypass it. The 20-test pytest suite isn't decorative — it's what CI actually runs on every push, and the badge above reflects the real, current state of that pipeline.

## What's tested (and why it matters)

`core/rules.py` holds all the business logic — task state transitions, the QA gate, sprint burndown math, and velocity — as **pure functions with zero database or UI coupling**. That's what makes `tests/test_rules.py`'s 20 tests possible without mocking anything. Coverage includes the edge cases that actually matter in a delivery tool:

- A task with **zero QA checks defined** does *not* pass the gate — an empty checklist isn't a satisfied one.
- Illegal state transitions (e.g., Backlog → Done, skipping QA Review entirely) raise before the QA gate is even evaluated.
- Burndown's "actual remaining" line doesn't project into the future beyond today — only the ideal line does.
- Velocity of zero completed sprints returns `0.0`, not an exception — "nothing shipped yet" is a normal state early in an engagement, not an error.

## Design decisions worth noting

- **SQLite, not Postgres.** This project's purpose is CI/testing discipline, and a test suite that depends on a live external database is slower and flakier than one that doesn't touch the network. SQLite is file-based, needs zero setup, and keeps `pytest` (and GitHub Actions) fast and fully self-contained. (My other project, the [HCP Targeting case study](https://github.com/Dhayalramesh/hcp-targeting-case-study), already demonstrates cloud Postgres and window-function SQL — this project intentionally emphasizes a different skill.)
- **Business logic is separated from persistence and UI on purpose.** `core/rules.py` never imports `db.py` or `streamlit`. That's not incidental structure — it's what makes the test suite possible without database fixtures or UI mocking.
- **Auto-seeding on first load.** SQLite is a local file, deliberately excluded from git (`.gitignore`) since committing a database file isn't good practice. That means a freshly deployed instance — like on Streamlit Community Cloud — always starts with an empty database, and there's no way to SSH in and run a seed script manually on a deployed container. `app.py` detects an empty database on load and seeds it automatically, so the deployed app and the local app behave identically with zero manual setup either way.

## Structure
core/
models.py -- plain dataclasses: Task, Sprint, Engagement, QACheck (no I/O)
rules.py -- pure business logic: transitions, QA gate, burndown, velocity
tests/
test_rules.py -- 20 unit tests covering core/rules.py
db.py -- SQLite persistence layer
seed_data.py -- sample data generator: 2 engagements, 4 sprints, 8 tasks in mixed states (also auto-invoked by app.py on empty database)
app.py -- Streamlit UI: sprint board, burndown, velocity
.github/workflows/
ci.yml -- runs pytest on every push/PR to main

## Setup

```bash
pip install -r requirements.txt
python seed_data.py
streamlit run app.py
```

(Seeding manually is optional — `app.py` will auto-seed on first run if the database is empty. The manual step is mainly useful if you want to reset to fresh sample data.)

## Running the tests

```bash
pip install pytest
pytest tests/ -v
```
