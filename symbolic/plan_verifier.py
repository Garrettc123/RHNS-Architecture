"""Deterministic, fail-closed validation for proposed RHNS action plans.

This module validates plans only. It never executes actions or calls external services.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


ALLOWED_OPERATIONS = frozenset({
    "read", "calculate", "classify", "validate", "draft", "propose"
})
BLOCKED_OPERATIONS = frozenset({
    "send_email", "send_sms", "charge", "transfer", "purchase",
    "deploy", "delete", "publish", "write_external", "execute"
})
MAX_ACTIONS = 25


@dataclass(frozen=True)
class Violation:
    rule_id: str
    severity: str
    message: str
    remediation: str
    action_id: str | None = None


@dataclass(frozen=True)
class VerificationResult:
    status: str
    approved: bool
    violations: tuple[Violation, ...]
    checked_actions: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "approved": self.approved,
            "violations": [asdict(item) for item in self.violations],
            "checked_actions": self.checked_actions,
        }


def verify_plan(plan: Any) -> VerificationResult:
    """Validate a JSON-like plan against deterministic, local policy rules."""
    violations: list[Violation] = []

    if not isinstance(plan, dict):
        return VerificationResult(
            "rejected", False,
            (Violation("PLAN-001", "error", "Plan must be a JSON object.",
                       "Submit an object containing a non-empty goal and actions list."),),
            0,
        )

    allowed_plan_fields = {"goal", "actions"}
    unknown_plan_fields = set(plan) - allowed_plan_fields
    if unknown_plan_fields:
        violations.append(Violation(
            "PLAN-005", "error",
            "Plan contains unsupported fields: " + ", ".join(sorted(map(str, unknown_plan_fields))),
            "Remove fields that are not part of the documented plan schema."
        ))

    goal = plan.get("goal")
    actions = plan.get("actions")

    if not isinstance(goal, str) or not goal.strip():
        violations.append(Violation(
            "PLAN-002", "error", "Goal must be a non-empty string.",
            "Provide a concise goal."
        ))

    elif len(goal) > 1000:
        violations.append(Violation(
            "PLAN-006", "error", "Goal exceeds the 1000-character limit.",
            "Use a concise goal of at most 1000 characters."
        ))

    if not isinstance(actions, list) or not actions:
        violations.append(Violation(
            "PLAN-003", "error", "Plan must contain at least one action.",
            "Provide one or more typed actions."
        ))
        actions = []
    elif len(actions) > MAX_ACTIONS:
        violations.append(Violation(
            "PLAN-004", "error", f"Plan exceeds the {MAX_ACTIONS}-action limit.",
            "Split the plan into smaller independently verifiable plans."
        ))

    seen_ids: set[str] = set()
    for index, action in enumerate(actions[:MAX_ACTIONS]):
        if not isinstance(action, dict):
            violations.append(Violation(
                "ACTION-001", "error", f"Action at index {index} must be an object.",
                "Provide action_id, operation, and target as strings."
            ))
            continue

        allowed_action_fields = {
            "action_id", "operation", "target",
            "external_effect", "requires_human_approval",
        }
        unknown_action_fields = set(action) - allowed_action_fields
        if unknown_action_fields:
            violations.append(Violation(
                "ACTION-005", "error",
                "Action contains unsupported fields: " + ", ".join(sorted(map(str, unknown_action_fields))),
                "Remove fields that are not part of the documented action schema.",
                action.get("action_id") if isinstance(action.get("action_id"), str) else None,
            ))

        action_id = action.get("action_id")
        operation = action.get("operation")
        target = action.get("target")
        label = action_id if isinstance(action_id, str) else None

        if not isinstance(action_id, str) or not action_id.strip():
            violations.append(Violation(
                "ACTION-002", "error", f"Action at index {index} has no valid action_id.",
                "Add a unique, non-empty action_id."
            ))
        elif action_id in seen_ids:
            violations.append(Violation(
                "ACTION-003", "error", f"Duplicate action_id: {action_id}.",
                "Give every action a unique identifier.", label
            ))
        else:
            seen_ids.add(action_id)

        if not isinstance(operation, str) or not operation.strip():
            violations.append(Violation(
                "POLICY-001", "error", "Action operation is missing or invalid.",
                "Choose an explicitly supported operation.", label
            ))
        elif operation in BLOCKED_OPERATIONS:
            violations.append(Violation(
                "POLICY-002", "error",
                f"Operation '{operation}' can create an external side effect and is blocked.",
                "Replace it with a draft or proposal; execution requires a separate authorized control plane.",
                label
            ))
        elif operation not in ALLOWED_OPERATIONS:
            violations.append(Violation(
                "POLICY-003", "error", f"Operation '{operation}' is not allowlisted.",
                "Use one of: " + ", ".join(sorted(ALLOWED_OPERATIONS)) + ".", label
            ))

        if not isinstance(target, str) or not target.strip():
            violations.append(Violation(
                "ACTION-004", "error", "Action target must be a non-empty string.",
                "Specify the resource or subject the action concerns.", label
            ))

        for flag_name in ("external_effect", "requires_human_approval"):
            if flag_name in action and not isinstance(action[flag_name], bool):
                violations.append(Violation(
                    "POLICY-006", "error",
                    f"Action field '{flag_name}' must be a boolean.",
                    "Use true or false explicitly.",
                    label,
                ))

        if isinstance(action_id, str) and len(action_id) > 128:
            violations.append(Violation(
                "ACTION-006", "error", "Action ID exceeds the 128-character limit.",
                "Use an action ID of at most 128 characters.", label
            ))

        if isinstance(operation, str) and len(operation) > 64:
            violations.append(Violation(
                "POLICY-007", "error", "Operation exceeds the 64-character limit.",
                "Use a supported operation name.", label
            ))

        if isinstance(target, str) and len(target) > 1024:
            violations.append(Violation(
                "ACTION-007", "error", "Action target exceeds the 1024-character limit.",
                "Use a concise target of at most 1024 characters.", label
            ))

        if action.get("external_effect") is True:
            violations.append(Violation(
                "POLICY-004", "error", "Actions marked external_effect=true are prohibited.",
                "Keep this plan read-only or produce a draft for human review.", label
            ))

        if action.get("requires_human_approval") is True:
            violations.append(Violation(
                "POLICY-005", "error", "Action requires human approval and cannot be auto-approved.",
                "Route the action to an explicit human approval workflow.", label
            ))

    approved = not violations
    return VerificationResult(
        "approved" if approved else "rejected",
        approved,
        tuple(violations),
        min(len(actions), MAX_ACTIONS),
    )
