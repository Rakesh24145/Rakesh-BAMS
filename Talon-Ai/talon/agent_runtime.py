"""Generic LLM agent loop (ReAct style): think -> call a tool -> read the result ->
repeat -> give a final answer. The model answers in JSON only.

Safety rules built in:
* tools are read-only;  * at most config.AGENT_MAX_STEPS tool calls;
* any bad/invalid output returns None, and the agent falls back to its
  rule-based answer;  * the caller validates everything the model returns."""
import json

from . import config, db, llm, observability

SYSTEM = """You are {name}, the {title} in a talent-intelligence platform.
Your goal: {goal}
Reply with exactly ONE JSON object and nothing else.
To use a tool:  {{"thought": "short reason", "action": "tool_name", "args": {{...}}}}
To finish:      {{"final": {{...}}}}
Available tools:
{tools}
Rules: use only facts that appear in tool results or the task; never invent skills,
scores or names; keep text short; a human will review your answer."""


def react(cid: int, agent, task: str, tools: dict, max_steps: int = None):
    """Returns (final_dict_or_None, trace_list)."""
    trace: list = []
    if not llm.available():
        return None, trace
    system = SYSTEM.format(
        name=agent.name, title=agent.title, goal=agent.goal,
        tools="\n".join("- " + d for _, d in tools.values()))
    convo = f"TASK: {task}\n"
    for _ in range(max_steps or config.AGENT_MAX_STEPS):
        out = llm.chat_json(agent.name, system, convo)
        if not isinstance(out, dict):
            trace.append({"error": "model did not return valid JSON"})
            break
        if isinstance(out.get("final"), dict):
            trace.append({"final": out["final"]})
            _save(cid, agent, trace)
            return out["final"], trace
        action = out.get("action")
        if action is None:                       # model answered directly
            trace.append({"final": out})
            _save(cid, agent, trace)
            return out, trace
        args = out.get("args") if isinstance(out.get("args"), dict) else {}
        if action not in tools:
            obs = f"Unknown tool {action!r}. Valid tools: {list(tools)}"
        else:
            try:
                obs = tools[action][0](**args)
            except Exception as exc:
                obs = f"Tool error: {exc}"
        observability.log(cid, agent.name, "tool_call", f"{action}({args})")
        trace.append({"thought": str(out.get("thought", ""))[:200], "action": action,
                      "args": args, "observation": str(obs)[:500]})
        convo += f"\nYOU: {json.dumps(out)}\nOBSERVATION: {obs}\n"
    _save(cid, agent, trace)
    return None, trace


def _save(cid, agent, trace) -> None:
    db.memory_set(cid, agent.name, "trace", trace)


def clean_text(value, limit: int = 600):
    """Accept the model's text only if it is a sensible string."""
    if isinstance(value, str) and 5 <= len(value.strip()) <= limit:
        return value.strip()
    return None
