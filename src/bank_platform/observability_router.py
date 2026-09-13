"""Staff-gated read access to Phase 8's usage log (observability.py /
AgentEventLog) - a data source, not a dashboard. Same auth pattern as
delete_account: this is operational data, not customer-facing.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func

from bank_platform.auth import get_current_staff_user
from bank_platform.database import SessionLocal
from bank_platform.models import AgentEventLog

router = APIRouter(prefix="/observability", tags=["observability"])


class UsageTotals(BaseModel):
    total_events: int
    llm_calls: int
    tool_calls: int
    total_tokens: int
    estimated_cost_usd: float
    failed_events: int


class DailyUsage(BaseModel):
    day: str
    llm_calls: int
    tool_calls: int
    total_tokens: int
    estimated_cost_usd: float


class UsageResponse(BaseModel):
    totals: UsageTotals
    by_day: list[DailyUsage]


@router.get("/usage", response_model=UsageResponse, dependencies=[Depends(get_current_staff_user)])
async def get_usage():
    db = SessionLocal()
    try:
        rows = db.query(AgentEventLog).all()
        total_tokens = sum(r.total_tokens or 0 for r in rows)
        estimated_cost_usd = sum(float(r.estimated_cost_usd or 0) for r in rows)
        totals = UsageTotals(
            total_events=len(rows),
            llm_calls=sum(1 for r in rows if r.event_type == "llm_call"),
            tool_calls=sum(1 for r in rows if r.event_type == "tool_call"),
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost_usd,
            failed_events=sum(1 for r in rows if not r.success),
        )

        day_expr = func.date(AgentEventLog.created_at)
        daily_rows = (
            db.query(
                day_expr.label("day"),
                AgentEventLog.event_type,
                func.count().label("count"),
                func.sum(AgentEventLog.total_tokens).label("tokens"),
                func.sum(AgentEventLog.estimated_cost_usd).label("cost"),
            )
            .group_by(day_expr, AgentEventLog.event_type)
            .order_by(day_expr)
            .all()
        )

        by_day: dict[str, DailyUsage] = {}
        for day, event_type, count, tokens, cost in daily_rows:
            day_str = str(day)
            entry = by_day.setdefault(
                day_str, DailyUsage(day=day_str, llm_calls=0, tool_calls=0, total_tokens=0, estimated_cost_usd=0.0)
            )
            if event_type == "llm_call":
                entry.llm_calls = count
                entry.total_tokens += tokens or 0
                entry.estimated_cost_usd += float(cost or 0)
            else:
                entry.tool_calls = count

        return UsageResponse(totals=totals, by_day=sorted(by_day.values(), key=lambda d: d.day))
    finally:
        db.close()
