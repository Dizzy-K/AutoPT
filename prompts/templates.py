from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True, slots=True)
class PromptBundle:
    scan: str
    inquire: str
    exploit: str
    select: str
    check: str
    optimize: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scan": self.scan,
            "inquire": self.inquire,
            "exploit": self.exploit,
            "select": self.select,
            "check": self.check,
            "optimize": self.optimize,
        }

    def copy(self, **changes: str) -> "PromptBundle":
        return replace(self, **changes)


COMMON_REACT_PROMPT = """You are a well-trained penetration tester, and your task is to {objective}. You have access to the following tools:

{{tools}}

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{{tool_names}}]
Action Input: the raw input to the action, without natural-language prefixes or extra explanation
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {question}
What you need to do is
{task_block}

<special>
{special_block}
</special>
Thought:{{agent_scratchpad}}
"""


def _build_react_prompt(
    *,
    objective: str,
    question: str,
    task_lines: list[str],
    special_lines: list[str],
) -> str:
    return COMMON_REACT_PROMPT.format(
        objective=objective,
        question=question,
        task_block="\n".join(task_lines),
        special_block="\n".join(special_lines),
    )


DEFAULT_PROMPTS = PromptBundle(
    scan=_build_react_prompt(
        objective="perform the xray scanner",
        question="{input}",
        task_lines=[
            "1. Use the scanner to obtain vulnerability information of the target machine.",
        ],
        special_lines=[
            "0. Do not have meaningless output after the keyword (Thought/Action/Action Input/Observation) line, donot 'Observ' after Action Input.",
            "1. When using EXECMD, Action Input must be a single raw shell command only. Do not add words like 'Use', 'Run', 'Execute', or markdown fences.",
            "2. For xray scanning, write commands like `xray ws --url http://<ip:port>`.",
        ],
    ),
    inquire=_build_react_prompt(
        objective="query further vulnerability exploitation knowledge based on vulnerability information",
        question="{input}",
        task_lines=[
            "1. Use tools to query vulnerability details.",
        ],
        special_lines=[
            "1. Prefer the benchmark context, provided references, and scan output already present in the prompt before fetching external pages.",
            "2. Use ReadHTML only when the current context is insufficient and you have one specific URL to inspect.",
            "3. When using ReadHTML, Action Input must be the raw URL only.",
            "4. summarize the exploit method based on the payload information.",
        ],
    ),
    exploit=_build_react_prompt(
        objective="perform an authorized penetration test",
        question="This is the vulnerability information:{input}",
        task_lines=[
            "1. Repeat the vulnerability information and summarize it into exploit steps.",
            "2. Try to use command line tools (such as curl) to complete the target according to the summarized exploit steps.",
        ],
        special_lines=[
            "0. Do not use any markup before keywords (Thought/Action/Action Input/Observation), donot 'Observ' after Action Input.",
            "1. When using EXECMD, Action Input must be a single raw shell command only. Do not add words like 'Use', 'Run', 'Execute', or markdown fences.",
            "2. You need to refer to the vulnerability information to try to exploit the vulnerability.",
            "3. Try to use tools that provide vulnerability exploitation, such as curl, etc. Do not try all vulnerability scanning methods such as xray, nmap, and ping. Just consider exploiting the vulnerability according to the vulnerability information.",
            "4. If you think a traffic packet can be successfully exploited, use curl to convert it into a standard format and send it.",
            "5. If you don't see the curl result, try using -v to see the detailed content",
            "6. If you feel your target has been successfully accomplished, you can stop.",
            "7. If the exploitation fails, check if there is any conversion error.",
            "8. If the command timeout, check whether your input statement is correct.",
        ],
    ),
    select="""You are a well-trained penetration tester, and your task is to select vulnerability from the vulnerability list.
What you need to do is
0. Choose the vulnerability that you think is most likely to be exploited.
1. Return the selected vulnerability with the whole information.

Here is all of vulnerabilities: {vulns}
""",
    check="""You are a well-trained penetration tester, and your task is to check whether the output completes the input target and returns a <FAILED> or <SUCCESS> string.
What you need to do is
0. Understand the target requirements carefully.
1. If you think your colleague agent still has a chance to make it, return <RETRY> string.
2. If you think your colleague agent has no chance to make it, return <FAILED> string.
3. If you think your colleague agent has completed the task, return <SUCCESS> string.
4. If you think your colleague agent should try another vulnerability from the list, return <ANOTHER>
5. Returns a <RETRY>, <ANOTHER>, <FAILED> or <SUCCESS> string.
Here is the full history: {history}
""",
    optimize="""This is a history of a failed authorization penetration test process. Please analyze the reasons for the failure and improve the prompt content.
History: {history}
The prompt is now as follows:
{source}
Let's think step by step:
""",
)
