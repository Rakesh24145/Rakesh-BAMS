"""Base class every TALON agent inherits from."""
from dataclasses import dataclass, field


@dataclass
class AgentResult:
    summary: str                       # one readable sentence for humans
    data: dict = field(default_factory=dict)   # structured output
    requires_approval: bool = False    # True = STOP and wait for a human
    approver_role: str = ""            # who must approve
    used_llm: bool = False


class BaseAgent:
    name = "BASE"
    title = ""
    goal = ""
    approver_role = "HR"

    def run(self, cand: dict, job: dict) -> AgentResult:  # pragma: no cover
        raise NotImplementedError
