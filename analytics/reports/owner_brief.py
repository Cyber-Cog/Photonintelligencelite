"""Owner-facing plain-language brief for PDF (and shared mapping with Results UI).

Mirrors frontend/src/lib/ownerActions.ts OWNER_COPY — keep problem/next-step
wording in sync when either side changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from analytics.core.result import ResultObject, ResultStatus

_SEVERITY_RANK = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}

_BLOCKED_PRIORITY = frozenset(
    {
        "disconnected_strings",
        "module_damage",
        "clipping_power",
        "clipping_current",
        "inverter_efficiency",
        "string_outlier",
    }
)

# (equipment, count, title) → plain-language problem sentence
_ProblemFn = Callable[[str, int, str], str]


def _equip_suffix(equipment: str) -> str:
    return f" ({equipment})" if equipment and equipment != "—" else ""


_OWNER_COPY: dict[str, tuple[_ProblemFn, str]] = {
    "disconnected_strings": (
        lambda equipment, count, _title: (
            f"{count} string groups look disconnected or offline (e.g. {equipment})."
            if count > 1
            else f"A string group looks disconnected or offline{_equip_suffix(equipment)}."
        ),
        "Check the listed SCB/strings on site, then review evidence to confirm the fault window.",
    ),
    "module_damage": (
        lambda equipment, count, _title: (
            f"{count} SCBs show voltage drop consistent with bypass diodes or module damage (e.g. {equipment})."
            if count > 1
            else f"Voltage drop suggests bypass diode or module damage{(' on ' + equipment) if equipment and equipment != '—' else ''}."
        ),
        "Inspect the affected modules for damage or diode activation; review evidence for the voltage reference.",
    ),
    "string_outlier": (
        lambda equipment, count, _title: (
            f"{count} strings/SCBs are running well below their peers (e.g. {equipment})."
            if count > 1
            else f"A string/SCB is running well below its peers{_equip_suffix(equipment)}."
        ),
        "Compare DC current on the peer group, then walk down the underperforming unit.",
    ),
    "clipping_power": (
        lambda equipment, count, _title: (
            f"{count} inverters are clipping at AC rating while irradiance could support more (e.g. {equipment})."
            if count > 1
            else f"Inverter clipping at AC rating{_equip_suffix(equipment)} — irradiance could support more output."
        ),
        "Confirm whether curtailment is intentional; compare DC/AC oversizing and inverter ratings in Setup.",
    ),
    "clipping_current": (
        lambda equipment, count, _title: (
            f"{count} SCB/MPPT paths show DC-side over-current clipping (e.g. {equipment})."
            if count > 1
            else f"DC-side current clipping detected{(' on ' + equipment) if equipment and equipment != '—' else ''}."
        ),
        "Validate architecture (strings per SCB), then review the clip windows in evidence.",
    ),
    "inverter_efficiency": (
        lambda equipment, count, _title: (
            f"{count} inverters show sustained conversion loss (e.g. {equipment})."
            if count > 1
            else f"Inverter conversion efficiency is below normal{_equip_suffix(equipment)}."
        ),
        "Review DC vs AC on the worst units and schedule inverter service if sustained.",
    ),
    "box_plot": (
        lambda _equipment, _count, _title: "Inverter efficiency spread looks unusual across the fleet.",
        "Compare efficiency outliers to peers in the diagnostics section.",
    ),
}


@dataclass
class OwnerProblem:
    algorithm_id: str
    problem: str
    impact_kwh: float | None
    severity: str | None
    next_step: str
    priority: int


@dataclass
class OwnerBrief:
    """Page-1 executive brief for asset owners."""

    status: str  # "Healthy" | "Needs attention" | "Critical"
    status_detail: str
    problems: list[OwnerProblem] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    total_loss_kwh: float = 0.0
    fault_module_count: int = 0


def _is_noise_recommendation(text: str) -> bool:
    low = text.lower().strip()
    if not low:
        return True
    noise = (
        "no dc current clipping",
        "no power clipping events",
        "no sustained voltage-deviation",
        "no distributional outliers",
        "tight and consistent across inverters",
        "this is a v1 algorithm",
        "treat magnitudes as directional",
        "no events detected",
        "no inverter showed",
        "no scb/mppt showed",
    )
    if any(frag in low for frag in noise):
        return True
    if low.startswith("no ") and ("detected" in low or "showed" in low or "require action" in low):
        return True
    return False


def _first_actionable_rec(recs: list[str]) -> str | None:
    for rec in recs:
        if not _is_noise_recommendation(rec):
            return rec.strip()
    return None


def _has_real_findings(r: ResultObject) -> bool:
    if r.status != ResultStatus.OK:
        return False
    if (r.loss_energy_kwh or 0) > 0:
        return True
    if r.affected_equipment:
        return True
    sev = (r.severity or "").lower()
    if sev in ("low", "medium", "high", "critical") and any(t.rows for t in r.tables):
        return True
    return False


def _equipment_sample(r: ResultObject, *, limit: int = 2) -> str:
    if r.affected_equipment:
        sample = ", ".join(r.affected_equipment[:limit])
        return sample
    for table in r.tables:
        lower = {c.lower(): i for i, c in enumerate(table.columns)}
        eq_i = None
        for cand in ("scb", "scb/mppt", "inverter", "unit", "equipment"):
            if cand in lower:
                eq_i = lower[cand]
                break
        if eq_i is None:
            continue
        names: list[str] = []
        for raw in table.rows:
            if eq_i < len(raw) and raw[eq_i] not in (None, "", "—"):
                names.append(str(raw[eq_i]))
            if len(names) >= limit:
                break
        if names:
            return ", ".join(names)
    return "—"


def _finding_count(r: ResultObject) -> int:
    n = sum(len(t.rows) for t in r.tables if t.rows)
    if n > 0:
        return n
    if r.affected_equipment:
        return len(r.affected_equipment)
    return 1 if _has_real_findings(r) else 0


def _problem_text(r: ResultObject) -> str:
    copy = _OWNER_COPY.get(r.algorithm_id)
    equipment = _equipment_sample(r)
    count = _finding_count(r)
    if copy:
        fn, _ = copy
        return fn(equipment, count, r.title)
    if r.summary and r.summary.strip():
        return r.summary.strip()
    return f"{r.title}: {count} finding(s) need review."


def _next_for_result(r: ResultObject) -> str:
    rec = _first_actionable_rec(r.recommendations)
    if rec:
        return rec
    copy = _OWNER_COPY.get(r.algorithm_id)
    if copy:
        return copy[1]
    return "Review the finding evidence, then schedule a site check if confirmed."


def _human_missing(summary: str) -> str:
    cleaned = " ".join(summary.split()).strip()
    if not cleaned:
        return "Required inputs are missing for this check."
    return (
        cleaned.replace("Unavailable:", "")
        .replace("unavailable:", "")
        .replace("SCADA", "plant data")
        .replace("POA", "plane-of-array irradiance")
        .replace("GHI", "global horizontal irradiance")
        .strip()
    )


def _blocked_next(r: ResultObject) -> str:
    missing = _human_missing(r.summary or r.error or "")
    return f"{missing} Fix the missing inputs in Setup, then re-run analysis."


def derive_plant_status(results: list[ResultObject]) -> tuple[str, str]:
    """Return (Healthy|Needs attention|Critical, short detail)."""
    findings = [r for r in results if _has_real_findings(r)]
    if not findings:
        return "Healthy", "No confirmed faults in this analysis window."

    severities = [(r.severity or "medium").lower() for r in findings]
    ranks = [_SEVERITY_RANK.get(s, 2) for s in severities]
    worst = min(ranks)
    n = len(findings)
    total_loss = sum((r.loss_energy_kwh or 0.0) for r in findings)

    if worst == 0 or (worst == 1 and n >= 3):
        detail = f"{n} issue module(s) · worst severity critical/high"
        if total_loss > 0:
            detail += f" · ~{total_loss:,.0f} kWh estimated loss"
        return "Critical", detail

    detail = f"{n} issue module(s) need review"
    if total_loss > 0:
        detail += f" · ~{total_loss:,.0f} kWh estimated loss"
    return "Needs attention", detail


def build_owner_brief(results: list[ResultObject], *, max_problems: int = 3, max_next: int = 4) -> OwnerBrief:
    """Build prioritized owner problems + next steps from algorithm results."""
    status, status_detail = derive_plant_status(results)
    findings = [r for r in results if _has_real_findings(r)]

    problems: list[OwnerProblem] = []
    for r in findings:
        sev = (r.severity or "medium").lower()
        sev_rank = _SEVERITY_RANK.get(sev, 2)
        problems.append(
            OwnerProblem(
                algorithm_id=r.algorithm_id,
                problem=_problem_text(r),
                impact_kwh=float(r.loss_energy_kwh) if r.loss_energy_kwh is not None else None,
                severity=r.severity,
                next_step=_next_for_result(r),
                priority=10 + sev_rank,
            )
        )

    problems.sort(key=lambda p: (p.priority, -(p.impact_kwh or 0.0), p.algorithm_id))
    top = problems[:max_problems]

    next_steps: list[str] = []
    seen: set[str] = set()

    def _add_step(text: str) -> None:
        key = text.lower().strip()
        if not key or key in seen:
            return
        seen.add(key)
        next_steps.append(text.strip())

    for p in top:
        _add_step(p.next_step)

    # Blocked priority modules → setup next steps (after fault actions)
    for r in results:
        if len(next_steps) >= max_next:
            break
        if r.status not in (ResultStatus.UNAVAILABLE, ResultStatus.ERROR):
            continue
        if r.status != ResultStatus.ERROR and r.algorithm_id not in _BLOCKED_PRIORITY:
            continue
        if r.status == ResultStatus.ERROR:
            _add_step(
                r.summary.strip()
                if r.summary and r.summary.strip()
                else f"{r.title}: re-check Setup inputs and re-run analysis."
            )
        else:
            _add_step(_blocked_next(r))

    total_loss = sum((r.loss_energy_kwh or 0.0) for r in findings)
    return OwnerBrief(
        status=status,
        status_detail=status_detail,
        problems=top,
        next_steps=next_steps[:max_next],
        total_loss_kwh=total_loss,
        fault_module_count=len(findings),
    )
