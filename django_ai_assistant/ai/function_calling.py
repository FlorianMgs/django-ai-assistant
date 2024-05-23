import json
from typing import override

from openai import AssistantEventHandler, OpenAI
from openai.types.beta.assistant_stream_event import ThreadRunRequiresAction
from openai.types.beta.threads.run import Run

from .function_tool import FunctionTool, call_tool


class EventHandler(AssistantEventHandler):
    tools_by_name: dict[str, FunctionTool]

    def __init__(self, client: OpenAI, tools: list[FunctionTool]) -> None:
        self.client = client
        self.tools_by_name = {tool.metadata.name: tool for tool in tools}
        super().__init__()

    @override
    def on_event(self, event: ThreadRunRequiresAction):
        # Retrieve events that are denoted with 'requires_action'
        # since these will have our tool_calls
        if event.event == "thread.run.requires_action":
            run_id = event.data.id  # Retrieve the run ID from the event data
            self.handle_requires_action(event.data, run_id)

    def handle_requires_action(self, data: Run, run_id: str):
        output_str_list: list[str] = []

        for tool_call in data.required_action.submit_tool_outputs.tool_calls:
            if tool_call.type != "function":
                raise Exception(f"Unexpected tool_call.type={tool_call.type}")
            tool = self.tools_by_name[tool_call.function.name]
            try:
                # TODO: check how properly handle empty arguments:
                #       search for .function.arguments in llamaindex
                if tool_call.function.arguments == "":
                    tool_kwargs = {}
                else:
                    tool_kwargs = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError as e:
                raise Exception(
                    f"Failed to parse tool arguments: {tool_call.function.arguments}"
                ) from e

            output = call_tool(tool, tool_kwargs)
            output_str_list.append({"tool_call_id": tool_call.id, "output": str(output)})

        # Submit all tool_outputs at the same time
        self.submit_tool_outputs(output_str_list, run_id)

    def submit_tool_outputs(self, tool_outputs, run_id):
        # Use the submit_tool_outputs_stream helper
        with self.client.beta.threads.runs.submit_tool_outputs_stream(
            thread_id=self.current_run.thread_id,
            run_id=self.current_run.id,
            tool_outputs=tool_outputs,
            event_handler=EventHandler(client=self.client, tools=self.tools_by_name.values()),
        ) as stream:
            # TODO: handle streaming
            for _text in stream.text_deltas:
                pass