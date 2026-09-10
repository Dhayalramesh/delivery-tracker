"""
Business rules for the Engagement Delivery Tracker.

Every function here is pure: it takes plain data in, returns plain data
out, and touches no database or UI. This is what makes the pytest suite
in tests/test_rules.py possible without any mocking — the whole point of
separating this from db.py and app.py.
"""

from dataclasses import replace
from datetime import date, timedelta

from core.models import Task, TaskStatus, QACheck, Sprint, VALID_TRANSITIONS


# ============================================================
# Task state machine
# ============================================================

def can_transition(current: TaskStatus, new: TaskStatus) -> bool:
    """Is moving from `current` to `new` a legal transition?"""
    return new in VALID_TRANSITIONS[current]


def qa_gate_passed(task: Task) -> bool:
    """A task's QA gate passes only if it has at least one QA check
    defined AND every defined check is marked passed. A task with zero
    QA checks defined has NOT passed the gate — an empty checklist is
    not the same as a satisfied one, and treating it as satisfied would
    silently defeat the whole point of an embedded QA procedure."""
    if not task.qa_checks:
        return False
    return all(check.passed for check in task.qa_checks)


def transition_task(task: Task, new_status: TaskStatus, today: date | None = None) -> Task:
    """Attempt to move a task to a new status. Raises ValueError on any
    illegal move, including the specific case of trying to reach Done
    without a passed QA gate — that check is enforced here, not left to
    the caller to remember."""
    if not can_transition(task.status, new_status):
        raise ValueError(
            f"Cannot move task '{task.title}' from {task.status.value} to {new_status.value}: "
            f"not a valid transition."
        )
    if new_status == TaskStatus.DONE and not qa_gate_passed(task):
        raise ValueError(
            f"Cannot mark '{task.title}' Done: QA gate not passed "
            f"({sum(1 for c in task.qa_checks if c.passed)}/{len(task.qa_checks)} checks passed)."
        )
    completed = (today or date.today()) if new_status == TaskStatus.DONE else task.completed_date
    return replace(task, status=new_status, completed_date=completed)


def qa_gate_summary(task: Task) -> dict:
    """Counts for displaying QA gate progress in the UI."""
    total = len(task.qa_checks)
    passed = sum(1 for c in task.qa_checks if c.passed)
    return {
        "total": total,
        "passed": passed,
        "failed_or_pending": total - passed,
        "gate_passed": qa_gate_passed(task),
    }


# ============================================================
# Sprint burndown
# ============================================================

def sprint_burndown(sprint: Sprint, tasks: list[Task], today: date | None = None) -> dict:
    """Computes an ideal linear burndown line and the actual remaining
    points per day, for the tasks belonging to this sprint.

    Ideal line: total points decreasing linearly from day 0 to the last day.
    Actual line: total points minus whatever had completed_date <= that day.
    """
    today = today or date.today()
    total_points = sum(t.story_points for t in tasks)
    sprint_days = (sprint.end_date - sprint.start_date).days
    if sprint_days <= 0:
        raise ValueError("Sprint end_date must be after start_date.")

    day_labels = [sprint.start_date + timedelta(days=i) for i in range(sprint_days + 1)]

    ideal = [
        round(total_points - (total_points * i / sprint_days), 1)
        for i in range(sprint_days + 1)
    ]

    actual = []
    for day in day_labels:
        completed_by_day = sum(
            t.story_points for t in tasks
            if t.completed_date is not None and t.completed_date <= day
        )
        remaining = total_points - completed_by_day
        # Don't project actual remaining points into the future beyond today
        actual.append(remaining if day <= today else None)

    return {
        "days": day_labels,
        "ideal_remaining": ideal,
        "actual_remaining": actual,
        "total_points": total_points,
    }


# ============================================================
# Velocity
# ============================================================

def sprint_completed_points(tasks: list[Task]) -> int:
    """Points completed (status == Done) within a single sprint's task list."""
    return sum(t.story_points for t in tasks if t.status == TaskStatus.DONE)


def velocity(points_per_sprint: list[int]) -> float:
    """Average completed points per sprint, across however many sprints
    are passed in. Returns 0 for an empty list rather than raising, since
    "no sprints completed yet" is a normal, expected state early in an
    engagement, not an error condition."""
    if not points_per_sprint:
        return 0.0
    return round(sum(points_per_sprint) / len(points_per_sprint), 1)