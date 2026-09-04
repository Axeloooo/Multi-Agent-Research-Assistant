from typing import Any, TypeAlias

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware.types import (
    AgentState,
    InputAgentState,
    OutputAgentState,
)
from langchain.chat_models import BaseChatModel, init_chat_model
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from langgraph.graph.state import CompiledStateGraph

from backend.src.tools.tools import scrape_url, web_search

load_dotenv()

AgentGraph: TypeAlias = CompiledStateGraph[
    AgentState[Any], Any, InputAgentState, OutputAgentState[Any]
]


def build_search_agent() -> AgentGraph:
    """Build a search agent that can perform web searches.

    Returns:
        An agent configured with the web search tool.
    """
    return create_agent(model="google_genai:gemini-3.5-flash-lite", tools=[web_search])


def build_reader_agent() -> AgentGraph:
    """Build a reader agent that can scrape web pages.

    Returns:
        An agent configured with the web scraping tool.
    """
    return create_agent(model="google_genai:gemini-3.5-flash-lite", tools=[scrape_url])


writer_prompt: ChatPromptTemplate = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an expert research writer. Write clear, structured and "
            "insightful reports.",
        ),
        (
            "human",
            """Write a detailed research report on the topic below.

Topic: {topic}

Research Gathered:
{research}

Structure the report as:
- Introduction
- Key Findings (minimum 3 well-explained points)
- Conclusion
- Sources (list all URLs found in the research)

Be detailed, factual and professional.""",
        ),
    ]
)

critic_prompt: ChatPromptTemplate = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a sharp and constructive research critic. Be honest and "
            "specific.",
        ),
        (
            "human",
            """Review the research report below and evaluate it strictly.

Report:
{report}

Respond in this exact format:

Score: X/10

Strengths:
- ...
- ...

Areas to Improve:
- ...
- ...

One line verdict:
...""",
        ),
    ]
)


def _build_model() -> BaseChatModel:
    """Create the configured Gemini model only when a stage needs it."""
    return init_chat_model(model="google_genai:gemini-3.5-flash-lite")


def build_writer_chain() -> RunnableSerializable[dict[str, Any], str]:
    """Build the report-generation chain."""
    return writer_prompt | _build_model() | StrOutputParser()


def build_critic_chain() -> RunnableSerializable[dict[str, Any], str]:
    """Build the report-critique chain."""
    return critic_prompt | _build_model() | StrOutputParser()
