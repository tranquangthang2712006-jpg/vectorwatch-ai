"""Giao diện chung của các Agent chuyên biệt."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .tools import ToolRunner


@dataclass
class TaskContext:
    """Trạng thái làm việc (working memory) của một nhiệm vụ, truyền giữa các Agent."""
    task_id: str
    trace_id: str
    user_name: str
    area_ids: list[int]
    start: str
    end: str
    species: str
    sources: list[str]
    tools: ToolRunner
    state: dict[str, Any] = field(default_factory=dict)


@dataclass
class StepResult:
    summary: str
    detail: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class BaseAgent:
    name = "Agent"
    role = ""

    def call(self, ctx: TaskContext, tool: str, **kwargs: Any) -> dict:
        return ctx.tools.call(self.name, tool, **kwargs)
