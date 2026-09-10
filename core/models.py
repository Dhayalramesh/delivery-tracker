"""
Domain models for the Engagement Delivery Tracker.

Kept as plain dataclasses with no framework or database coupling, so the
business logic in rules.py can be unit tested without a database, a
Streamlit session, or any I/O at all.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class TaskStatus(str, Enum):
    BACKLOG = "Backlog"
    IN_PROGRESS = "In Progress"
    QA_REVIEW = "QA Review"
    DONE = "Done"


# The only status transitions considered valid. A task must move through
# QA Review before it can reach Done — this is the "embedded QA procedure"
# enforced structurally, not just by convention.
VALID_TRANSITIONS = {
    TaskStatus.BACKLOG: {TaskStatus.IN_PROGRESS},
    TaskStatus.IN_PROGRESS: {TaskStatus.QA_REVIEW, TaskStatus.BACKLOG},
    TaskStatus.QA_REVIEW: {TaskStatus.DONE, TaskStatus.IN_PROGRESS},
    TaskStatus.DONE: set(),  # terminal state; reopening is a deliberate non-goal for v1
}


@dataclass
class QACheck:
    name: str
    passed: bool = False
    checked_by: str = ""


@dataclass
class Task:
    id: int
    sprint_id: int
    title: str
    owner: str
    story_points: int
    status: TaskStatus = TaskStatus.BACKLOG
    qa_checks: list[QACheck] = field(default_factory=list)
    completed_date: date | None = None


@dataclass
class Sprint:
    id: int
    engagement_id: int
    sprint_number: int
    goal: str
    start_date: date
    end_date: date


@dataclass
class Engagement:
    id: int
    client_name: str
    engagement_name: str
    start_date: date
    end_date: date