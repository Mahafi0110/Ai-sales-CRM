"""The LangGraph workflow:  START -> agent -> (tools -> agent)* -> END

  agent: the AI reads the conversation and either answers or asks for tools
  tools: we run the requested tools (with limits) and hand the results back
The loop stops when the AI answers, or when the step budget is used up.
"""
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.agent.prompts import BUDGET_NOTE


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    steps: int


def message_text(message) -> str:
    """Models may return plain text or a list of content blocks; always give back plain text."""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    parts = [block if isinstance(block, str) else block.get("text", "") for block in content
             if isinstance(block, (str, dict)) and (isinstance(block, str) or block.get("type", "text") == "text")]
    return "".join(parts).strip()


def build_graph(llm, tools: list, system_prompt: str, max_steps: int, trace: list):
    llm_with_tools = llm.bind_tools(tools)
    by_name = {tool.name: tool for tool in tools}

    def agent(state: AgentState):
        steps = state["steps"]
        last_chance = steps >= max_steps - 1
        system = system_prompt + (BUDGET_NOTE if last_chance else "")
        reply = llm_with_tools.invoke([SystemMessage(content=system)] + state["messages"])
        return {"messages": [reply], "steps": steps + 1}

    def run_tools(state: AgentState):
        results = []
        for call in state["messages"][-1].tool_calls:
            tool = by_name.get(call["name"])
            if tool is None:
                trace.append({"tool": call["name"], "args": call.get("args"), "ok": False,
                              "summary": "Unknown tool", "link": None})
                content = f"Error: there is no tool called '{call['name']}'."
            else:
                try:
                    content = tool.invoke(call.get("args") or {})
                except (ValueError, TypeError) as exc:  # arguments that do not fit the tool
                    trace.append({"tool": call["name"], "args": call.get("args"), "ok": False,
                                  "summary": "Invalid arguments", "link": None})
                    content = f"Error: invalid arguments ({str(exc)[:200]})"
            results.append(ToolMessage(content=content, tool_call_id=call["id"], name=call["name"]))
        return {"messages": results}

    def route(state: AgentState):
        last = state["messages"][-1]
        wants_tools = isinstance(last, AIMessage) and bool(last.tool_calls)
        return "tools" if wants_tools and state["steps"] < max_steps else END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent)
    graph.add_node("tools", run_tools)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()
