from agents import RunContextWrapper

from .types import AgentContext, append_tool_trace


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
) -> None:
    await emit_event(
        ctx,
        {
            "type": "tool_started",
            "tool_name": tool_name,
            "summary": summary,
        },
    )


async def record_tool_trace(
    ctx: RunContextWrapper[AgentContext],
    tool_name: str,
    status: str,
    summary: str,
) -> None:
    append_tool_trace(ctx, tool_name, status, summary)
    await emit_event(
        ctx,
        {
            "type": "tool_finished" if status == "ok" else "tool_failed",
            "tool_name": tool_name,
            "status": status,
            "summary": summary,
        },
    )
