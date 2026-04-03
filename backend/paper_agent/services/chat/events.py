from agents import RunContextWrapper

from .types import AgentContext, append_tool_trace, finish_tool_span, start_tool_span


async def emit_event(
    ctx: RunContextWrapper[AgentContext],
    event: dict[str, object],
) -> None:
    if ctx.context.event_emitter:
        await ctx.context.event_emitter(event)


async def emit_tool_started(
    ctx: RunContextWrapper[AgentContext],
    tool_name: str,
    summary: str,
    details: dict[str, object] | None = None,
) -> None:
    span = start_tool_span(ctx, tool_name)
    await emit_event(
        ctx,
        {
            "type": "tool_started",
            "trace_id": span.trace_id,
            "tool_name": tool_name,
            "summary": summary,
            "started_at": span.started_at,
            "details": details,
        },
    )


async def record_tool_trace(
    ctx: RunContextWrapper[AgentContext],
    tool_name: str,
    status: str,
    summary: str,
    details: dict[str, object] | None = None,
) -> None:
    trace_id, started_at, ended_at, duration_ms = finish_tool_span(ctx, tool_name)
    append_tool_trace(
        ctx,
        trace_id=trace_id,
        tool_name=tool_name,
        status=status,
        summary=summary,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        details=details,
    )
    tool_trace = ctx.context.tool_traces[-1]
    await emit_event(
        ctx,
        {
            "type": "tool_finished" if status == "ok" else "tool_failed",
            "trace_id": trace_id,
            "tool_name": tool_name,
            "status": status,
            "summary": summary,
            "tool_trace": tool_trace.model_dump(),
        },
    )
