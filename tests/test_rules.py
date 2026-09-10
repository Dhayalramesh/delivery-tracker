"""
Unit tests for core/rules.py.

Every test here exercises the pure business logic directly — no database,
no Streamlit, no mocking required, because rules.py takes plain data in
and returns plain data out. This is the payoff of keeping business logic
separate from I/O.
"""

from datetime import date, timedelta

import pytest

from core.models import Task, TaskStatus, QACheck, Sprint
from core.rules import (
    can_transition,
    qa_gate_passed,
    transition_task,
    qa_gate_summary,
    sprint_burndown,
    sprint_completed_points,
    velocity,
)


# ---------------- fixtures ----------------

def make_task(status=TaskStatus.BACKLOG, qa_checks=None, points=5, completed_date=None):
    return Task(
        id=1,
        sprint_id=1,
        title="Build client dashboard",
        owner="A. Consultant",
        story_points=points,
        status=status,
        qa_checks=qa_checks or [],
        completed_date=completed_date,
    )


# ---------------- state machine ----------------

class TestTransitions:
    def test_valid_forward_sequence(self):
        assert can_transition(TaskStatus.BACKLOG, TaskStatus.IN_PROGRESS)
        assert can_transition(TaskStatus.IN_PROGRESS, TaskStatus.QA_REVIEW)
        assert can_transition(TaskStatus.QA_REVIEW, TaskStatus.DONE)

    def test_cannot_skip_qa_review(self):
        # Backlog -> Done directly should never be legal, regardless of
        # QA check state — the gate only matters if you can even reach it.
        assert not can_transition(TaskStatus.BACKLOG, TaskStatus.DONE)

    def test_cannot_skip_in_progress(self):
        assert not can_transition(TaskStatus.BACKLOG, TaskStatus.QA_REVIEW)

    def test_done_is_terminal(self):
        assert not can_transition(TaskStatus.DONE, TaskStatus.IN_PROGRESS)
        assert not can_transition(TaskStatus.DONE, TaskStatus.BACKLOG)

    def test_can_move_backward_from_in_progress_to_backlog(self):
        # Real sprints deprioritize things; this should be allowed.
        assert can_transition(TaskStatus.IN_PROGRESS, TaskStatus.BACKLOG)


# ---------------- QA gate ----------------

class TestQAGate:
    def test_no_qa_checks_means_gate_not_passed(self):
        # This is the important edge case: an empty checklist must NOT
        # be treated as an automatically-satisfied one.
        task = make_task(qa_checks=[])
        assert qa_gate_passed(task) is False

    def test_all_checks_passed_means_gate_passed(self):
        task = make_task(qa_checks=[
            QACheck("Code reviewed", passed=True),
            QACheck("Tested against client sample data", passed=True),
        ])
        assert qa_gate_passed(task) is True

    def test_one_failed_check_blocks_gate(self):
        task = make_task(qa_checks=[
            QACheck("Code reviewed", passed=True),
            QACheck("Tested against client sample data", passed=False),
        ])
        assert qa_gate_passed(task) is False

    def test_gate_summary_counts(self):
        task = make_task(qa_checks=[
            QACheck("Code reviewed", passed=True),
            QACheck("Tested against client sample data", passed=False),
            QACheck("Client sign-off", passed=False),
        ])
        summary = qa_gate_summary(task)
        assert summary == {
            "total": 3,
            "passed": 1,
            "failed_or_pending": 2,
            "gate_passed": False,
        }


# ---------------- transition_task (combines state machine + QA gate) ----------------

class TestTransitionTask:
    def test_cannot_mark_done_without_passed_qa_gate(self):
        task = make_task(
            status=TaskStatus.QA_REVIEW,
            qa_checks=[QACheck("Client sign-off", passed=False)],
        )
        with pytest.raises(ValueError, match="QA gate not passed"):
            transition_task(task, TaskStatus.DONE)

    def test_can_mark_done_when_qa_gate_passed(self):
        task = make_task(
            status=TaskStatus.QA_REVIEW,
            qa_checks=[QACheck("Client sign-off", passed=True)],
        )
        today = date(2026, 6, 15)
        result = transition_task(task, TaskStatus.DONE, today=today)
        assert result.status == TaskStatus.DONE
        assert result.completed_date == today

    def test_illegal_transition_raises_before_qa_check(self):
        # Backlog -> Done should fail on "not a valid transition", not
        # get as far as evaluating the QA gate.
        task = make_task(status=TaskStatus.BACKLOG, qa_checks=[])
        with pytest.raises(ValueError, match="not a valid transition"):
            transition_task(task, TaskStatus.DONE)

    def test_completed_date_not_set_for_non_done_transitions(self):
        task = make_task(status=TaskStatus.BACKLOG)
        result = transition_task(task, TaskStatus.IN_PROGRESS)
        assert result.completed_date is None


# ---------------- sprint burndown ----------------

class TestSprintBurndown:
    def test_ideal_line_decreases_linearly_to_zero(self):
        sprint = Sprint(
            id=1, engagement_id=1, sprint_number=1, goal="Test sprint",
            start_date=date(2026, 6, 1), end_date=date(2026, 6, 11),  # 10-day sprint
        )
        tasks = [make_task(points=10)]
        result = sprint_burndown(sprint, tasks, today=date(2026, 6, 11))
        assert result["total_points"] == 10
        assert result["ideal_remaining"][0] == 10.0
        assert result["ideal_remaining"][-1] == 0.0
        # Midpoint should be roughly half
        assert result["ideal_remaining"][5] == pytest.approx(5.0)

    def test_actual_remaining_drops_when_task_completes(self):
        sprint = Sprint(
            id=1, engagement_id=1, sprint_number=1, goal="Test sprint",
            start_date=date(2026, 6, 1), end_date=date(2026, 6, 5),
        )
        tasks = [
            make_task(points=5, status=TaskStatus.DONE, completed_date=date(2026, 6, 3)),
            make_task(points=5, status=TaskStatus.IN_PROGRESS),
        ]
        result = sprint_burndown(sprint, tasks, today=date(2026, 6, 5))
        # Day 0 (June 1): nothing completed yet -> 10 remaining
        assert result["actual_remaining"][0] == 10
        # Day 2 (June 3): first task completed -> 5 remaining
        assert result["actual_remaining"][2] == 5

    def test_actual_remaining_is_none_beyond_today(self):
        sprint = Sprint(
            id=1, engagement_id=1, sprint_number=1, goal="Test sprint",
            start_date=date(2026, 6, 1), end_date=date(2026, 6, 10),
        )
        tasks = [make_task(points=5)]
        # "today" is partway through the sprint
        result = sprint_burndown(sprint, tasks, today=date(2026, 6, 3))
        day_index_for_today = (date(2026, 6, 3) - date(2026, 6, 1)).days
        assert result["actual_remaining"][day_index_for_today] is not None
        assert result["actual_remaining"][day_index_for_today + 1] is None

    def test_invalid_sprint_dates_raise(self):
        sprint = Sprint(
            id=1, engagement_id=1, sprint_number=1, goal="Bad sprint",
            start_date=date(2026, 6, 10), end_date=date(2026, 6, 1),
        )
        with pytest.raises(ValueError, match="end_date must be after"):
            sprint_burndown(sprint, [make_task()])


# ---------------- velocity ----------------

class TestVelocity:
    def test_velocity_averages_completed_points(self):
        assert velocity([20, 25, 15]) == 20.0

    def test_velocity_of_empty_list_is_zero_not_error(self):
        assert velocity([]) == 0.0

    def test_sprint_completed_points_ignores_non_done_tasks(self):
        tasks = [
            make_task(points=5, status=TaskStatus.DONE),
            make_task(points=8, status=TaskStatus.IN_PROGRESS),
            make_task(points=3, status=TaskStatus.DONE),
        ]
        assert sprint_completed_points(tasks) == 8