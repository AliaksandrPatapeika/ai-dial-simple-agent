import json
from typing import Any

import requests

from task.models.message import Message
from task.models.role import Role
from task.tools.base import BaseTool


class DialClient:

    def __init__(
            self,
            endpoint: str,
            deployment_name: str,
            api_key: str,
            tools: list[BaseTool] | None = None
    ):
        if not api_key:
            raise ValueError("API key cannot be empty")

        self._endpoint = f"{endpoint}/openai/deployments/{deployment_name}/chat/completions"
        self._api_key = api_key

        self._tools_dict = {tool.name: tool for tool in tools} if tools else {}
        self._tools = [tool.to_schema() for tool in tools] if tools else []

        print(f"Endpoint: {self._endpoint}")
        if self._tools:
            print(f"Available tools: {[tool.name for tool in tools]}")


    def get_completion(self, messages: list[Message], print_request: bool = True) -> Message:
        headers = {
            "api-key": self._api_key,
            "Content-Type": "application/json"
        }

        request_data = {
            "messages": [msg.to_dict() for msg in messages],
            "tools": self._tools
        }

        if print_request:
            print("REQUEST:")
            for msg in messages:
                print(f"  {msg.role}: {msg.content[:100]}..." if len(msg.content) > 100 else f"  {msg.role}: {msg.content}")

        response = requests.post(
            url=self._endpoint,
            headers=headers,
            json=request_data,
            timeout=60
        )

        if response.status_code == 200:
            response_json = response.json()
            choices = response_json.get("choices", [])
            choice = choices[0] if choices else None

            if choice:
                message_data = choice.get("message", {})
                content = message_data.get("content", "")
                tool_calls = message_data.get("tool_calls", [])

                ai_response = Message(
                    role=Role.ASSISTANT,
                    content=content,
                    tool_calls=tool_calls
                )

                if choice.get("finish_reason") == "tool_calls":
                    messages.append(ai_response)
                    tool_messages = self._process_tool_calls(tool_calls)
                    messages.extend(tool_messages)
                    return self.get_completion(messages, print_request)
                else:
                    return ai_response

        raise Exception(f"HTTP {response.status_code}: {response.text}")


    def _process_tool_calls(self, tool_calls: list[dict[str, Any]]) -> list[Message]:
        """Process tool calls and add results to messages."""
        tool_messages = []
        for tool_call in tool_calls:
            tool_call_id = tool_call.get("id")
            function = tool_call.get("function", {})
            function_name = function.get("name")
            arguments = json.loads(function.get("arguments", "{}"))

            tool_execution_result = self._call_tool(function_name, arguments)

            tool_messages.append(Message(
                role=Role.TOOL,
                name=function_name,
                tool_call_id=tool_call_id,
                content=tool_execution_result
            ))

            print(f"FUNCTION '{function_name}'\n{tool_execution_result}\n{'-'*50}")

        return tool_messages

    def _call_tool(self, function_name: str, arguments: dict[str, Any]) -> str:
        if function_name in self._tools_dict:
            tool = self._tools_dict[function_name]
            return tool.execute(**arguments)
        else:
            return f"Unknown function: {function_name}"
