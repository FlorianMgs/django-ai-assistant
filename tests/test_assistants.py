from typing import List

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, messages_to_dict
from langchain_core.retrievers import BaseRetriever

from django_ai_assistant.helpers.assistants import AIAssistant
from django_ai_assistant.models import Thread
from django_ai_assistant.tools import BaseModel, Field, method_tool


class TemperatureAssistant(AIAssistant):
    id = "temperature_assistant"  # noqa: A003
    name = "Temperature Assistant"
    description = "A temperature assistant that provides temperature information."
    instructions = "You are a temperature bot."
    model = "gpt-4o"

    def get_instructions(self):
        return self.instructions + " Today is 2024-06-09."

    @method_tool
    def fetch_current_temperature(self, location: str) -> str:
        """Fetch the current temperature data for a location"""
        return "32 degrees Celsius"

    class FetchForecastTemperatureInput(BaseModel):
        location: str
        dt_str: str = Field(description="Date in the format 'YYYY-MM-DD'")

    @method_tool(args_schema=FetchForecastTemperatureInput)
    def fetch_forecast_temperature(self, location: str, dt_str: str) -> str:
        """Fetch the forecast temperature data for a location"""
        return "35 degrees Celsius"


@pytest.mark.django_db(transaction=True)
@pytest.mark.vcr
def test_AIAssistant_invoke():
    thread = Thread.objects.create(name="Recife Temperature Chat")

    assistant = TemperatureAssistant()
    response_0 = assistant.invoke(
        {"input": "What is the temperature today in Recife?"},
        thread_id=thread.id,
    )
    response_1 = assistant.invoke(
        {"input": "What about tomorrow?"},
        thread_id=thread.id,
    )

    assert response_0 == {
        "history": [],
        "input": "What is the temperature today in Recife?",
        "output": "The current temperature in Recife today is 32 degrees Celsius.",
    }
    assert response_1 == {
        "history": [
            HumanMessage(content="What is the temperature today in Recife?"),
            AIMessage(content="The current temperature in Recife today is 32 degrees Celsius."),
        ],
        "input": "What about tomorrow?",
        "output": "The forecasted temperature in Recife for tomorrow, June 10, 2024, is "
        "expected to be 35 degrees Celsius.",
    }
    assert list(
        thread.messages.order_by("created_at").values_list("message", flat=True)
    ) == messages_to_dict(
        [
            HumanMessage(content="What is the temperature today in Recife?"),
            AIMessage(content="The current temperature in Recife today is 32 degrees Celsius."),
            HumanMessage(content="What about tomorrow?"),
            AIMessage(
                content="The forecasted temperature in Recife for tomorrow, June 10, 2024, is "
                "expected to be 35 degrees Celsius."
            ),
        ]
    )


class SequentialRetriever(BaseRetriever):
    sequential_responses: List[List[Document]]
    response_index: int = 0

    def _get_relevant_documents(self, query: str) -> List[Document]:
        if self.response_index >= len(self.sequential_responses):
            return []
        else:
            self.response_index += 1
            return self.sequential_responses[self.response_index - 1]

    async def _aget_relevant_documents(self, query: str) -> List[Document]:
        return self._get_relevant_documents(query)


class TourGuideAssistant(AIAssistant):
    id = "tour_guide_assistant"  # noqa: A003
    name = "Tour Guide Assistant"
    description = "A tour guide assistant that offers information about nearby attractions."
    instructions = (
        "You are a tour guide assistant offers information about nearby attractions. "
        "The user is at a location and wants to know what to learn about nearby attractions. "
        "Use the following pieces of context to suggest nearby attractions to the user. "
        "If there are no interesting attractions nearby, "
        "tell the user there's nothing to see where they're at. "
        "Use three sentences maximum and keep your suggestions concise."
        "\n\n"
        "---START OF CONTEXT---\n"
        "{context}"
        "---END OF CONTEXT---\n"
    )
    model = "gpt-4o"
    has_rag = True

    def get_retriever(self) -> BaseRetriever:
        return SequentialRetriever(
            sequential_responses=[
                [
                    Document(page_content="Central Park"),
                    Document(page_content="American Museum of Natural History"),
                ],
                [Document(page_content="Museum of Modern Art")],
            ]
        )


@pytest.mark.django_db(transaction=True)
@pytest.mark.vcr
def test_AIAssistant_with_rag_invoke():
    thread = Thread.objects.create(name="Tour Guide Chat")

    assistant = TourGuideAssistant()
    response_0 = assistant.invoke(
        {"input": "I'm at Central Park W & 79st, New York, NY 10024, United States."},
        thread_id=thread.id,
    )
    response_1 = assistant.invoke(
        {"input": "11 W 53rd St, New York, NY 10019, United States."},
        thread_id=thread.id,
    )

    assert response_0 == {
        "history": [],
        "input": "I'm at Central Park W & 79st, New York, NY 10024, United States.",
        "output": "You're right by the American Museum of Natural History, one of the "
        "largest museums in the world, featuring fascinating exhibits on "
        "dinosaurs, human origins, and outer space. Additionally, you're at the "
        "edge of Central Park, a sprawling urban oasis with scenic walking trails, "
        "lakes, and the iconic Central Park Zoo. Enjoy the blend of natural beauty "
        "and cultural richness!",
    }
    assert response_1 == {
        "history": [
            HumanMessage(content=response_0["input"]),
            AIMessage(content=response_0["output"]),
        ],
        "input": "11 W 53rd St, New York, NY 10019, United States.",
        "output": "You're at the location of the Museum of Modern Art (MoMA), home to an "
        "extensive collection of modern and contemporary art, including works by "
        "Van Gogh, Picasso, and Warhol. Nearby, you can also visit Rockefeller "
        "Center, known for its impressive architecture and the Top of the Rock "
        "observation deck. These attractions offer a blend of artistic and urban "
        "experiences.",
    }
    assert list(
        thread.messages.order_by("created_at").values_list("message", flat=True)
    ) == messages_to_dict(
        [
            HumanMessage(content=response_0["input"]),
            AIMessage(content=response_0["output"]),
            HumanMessage(content=response_1["input"]),
            AIMessage(content=response_1["output"]),
        ]
    )
