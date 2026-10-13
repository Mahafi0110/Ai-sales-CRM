"""Runs the assistant for one request and records everything it did."""
import logging
import time
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent import prompts
from app.agent.graph import build_graph, message_text
from app.agent.tools import ToolContext, build_tools
from app.ai.llm import get_llm, model_name
from app.ai.runner import translate_error
from app.core.config import get_settings
from app.models.agent import AgentRun
from app.models.user import User
from app.services import access, audit_service

log = logging.getLogger(__name__)


def runs_last_hour(db: Session, user: User) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    return db.scalar(select(func.count(AgentRun.id)).where(AgentRun.user_id == user.id,
                                                          AgentRun.created_at >= since)) or 0


def _fallback_answer(trace: list) -> str:
    done = [f"- {t['tool']}: {'ok' if t['ok'] else 'did not work'}" for t in trace[:12]]
    return ("I ran out of steps before I could finish, so I stopped here. This is what I did so far:\n"
            + ("\n".join(done) if done else "- nothing yet") + "\nAsk again, or ask for a smaller task, to continue.")


def run_agent(db: Session, user: User, message: str, request: Request | None = None) -> AgentRun:
    settings = get_settings()
    used = runs_last_hour(db, user)
    if used >= settings.agent_runs_per_hour:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"You have made {used} assistant requests in the last hour (the limit is "
                            f"{settings.agent_runs_per_hour}). Please wait a while.")
    llm = get_llm()  # raises a friendly error if no AI key is set; nothing is recorded in that case

    started = time.monotonic()
    run = AgentRun(user_id=user.id, prompt=message.strip(), ai_model=model_name(), status="running")
    db.add(run)
    db.commit()  # saved first, so anything the assistant proposes can point back to this run
    db.refresh(run)

    ctx = ToolContext(db=db, user=user, request=request, run_id=run.id)
    system = prompts.SYSTEM.format(name=user.full_name, role=user.role.replace("_", " "),
                                   today=date.today().strftime("%A %d %B %Y"))
    graph = build_graph(llm, build_tools(ctx), system, settings.agent_max_steps, ctx.trace)

    try:
        final = graph.invoke({"messages": [HumanMessage(content=message.strip())], "steps": 0},
                             config={"recursion_limit": 4 * settings.agent_max_steps + 6})
    except Exception as exc:
        error = exc if isinstance(exc, HTTPException) else translate_error(exc)
        run.status, run.error, run.trace = "failed", str(error.detail), ctx.trace
        run.duration_ms = int((time.monotonic() - started) * 1000)
        db.commit()
        audit_service.log_action(db, "ai_agent_run", user.id, "agent_run", run.id,
                                 {"status": "failed", "model": run.ai_model}, request)
        raise error from exc

    last = final["messages"][-1]
    text = message_text(last)
    unfinished = isinstance(last, AIMessage) and bool(last.tool_calls)
    run.status = "step_limit" if unfinished else "completed"
    if unfinished:
        run.answer = (text + "\n\n" if text else "") + _fallback_answer(ctx.trace)
    else:
        run.answer = text or "I could not produce an answer. Please try rephrasing."
    run.trace, run.steps = ctx.trace, final["steps"]
    run.duration_ms = int((time.monotonic() - started) * 1000)
    db.commit()
    db.refresh(run)
    audit_service.log_action(db, "ai_agent_run", user.id, "agent_run", run.id,
                             {"status": run.status, "model": run.ai_model, "steps": run.steps,
                              "tools": [t["tool"] for t in ctx.trace]}, request)
    return run


def list_runs(db: Session, user: User, limit: int = 30) -> list[AgentRun]:
    stmt = select(AgentRun)
    if not access.is_manager(user):
        stmt = stmt.where(AgentRun.user_id == user.id)
    return list(db.scalars(stmt.order_by(AgentRun.created_at.desc(), AgentRun.id.desc()).limit(limit)))


def get_run(db: Session, user: User, run_id: int) -> AgentRun:
    run = db.get(AgentRun, run_id)
    if not run:
        raise access.not_found("Assistant run")
    if not access.is_manager(user) and run.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this record")
    return run
