"""A tiny tool registry.

A "tool" is just a normal Python function plus a description and a JSON
schema of its inputs. The schema is what lets an LLM call the function: the
LLM reads the description, decides to use the tool, and writes JSON arguments
that match the schema; our code then runs the function and returns the result.

In offline mode the same functions are called directly by the rule-based
agents, so both modes share exactly the same tool code.
"""

import json
import time
from dataclasses import dataclass


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    function: callable        # function(trace, **arguments) -> JSON-serializable dict
    agent: str                # which agent owns this tool

    def to_anthropic(self):
        """The tool definition format expected by the Claude Messages API."""
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}

    def run(self, trace, arguments):
        start = time.time()
        try:
            result = self.function(trace, **arguments)
            error = False
        except Exception as exc:  # errors are returned to the caller, never hidden
            result = {"error": f"{type(exc).__name__}: {exc}"}
            error = True
        trace.step(self.agent, "called tool", self.name,
                   detail="error: " + result["error"] if error else summarize(result),
                   inputs=arguments, seconds=time.time() - start)
        return result, error


def summarize(result):
    text = json.dumps(result, default=str)
    return text[:300] + ("..." if len(text) > 300 else "")


def tool_result_text(result, limit=12000):
    """Tool results sent back to the LLM, truncated so they can't flood its context."""
    text = json.dumps(result, default=str)
    return text if len(text) <= limit else text[:limit] + '..."(truncated)"'
