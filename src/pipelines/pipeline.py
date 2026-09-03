from src.agents.agents import (
    build_search_agent,
    build_reader_agent,
    writer_chain,
    critic_chain,
)
from typing import Any, TypeAlias, Dict
from langchain.agents.middleware.types import (
    AgentState,
    InputAgentState,
    OutputAgentState,
)
from langgraph.graph.state import CompiledStateGraph

AgentGraph: TypeAlias = CompiledStateGraph[
    AgentState[Any], Any, InputAgentState, OutputAgentState[Any]
]


def run_research_pipeline(topic: str) -> Dict:
    state: Dict[str, str] = {}

    # step 1 - search agent
    print("\n" + " =" * 50)
    print("step 1 - search agent is working ...")
    print("=" * 50)

    search_agent: AgentGraph = build_search_agent()
    search_result: Dict[str, str] = search_agent.invoke(
        {
            "messages": [
                (
                    "user",
                    f"Find recent, reliable and detailed information about: {topic}",
                )
            ]
        }
    )
    state["search_results"] = "\n\n".join(
        str(message.content) for message in search_result["messages"]
    )

    print("\n search result ", state["search_results"])

    # step 2 - reader agent
    print("\n" + " =" * 50)
    print("step 2 - Reader agent is scraping top resources ...")
    print("=" * 50)

    reader_agent: AgentGraph = build_reader_agent()
    reader_result: Dict[str, str] = reader_agent.invoke(
        {
            "messages": [
                (
                    "user",
                    f"Based on the following search results about '{topic}', "
                    f"pick the most relevant URL and scrape it for deeper content.\n\n"
                    f"Search Results:\n{state['search_results']}",
                )
            ]
        }
    )

    state["scraped_content"] = reader_result["messages"][-1].content

    print("\nscraped content: \n", state["scraped_content"])

    # step 3 - writer chain
    print("\n" + " =" * 50)
    print("step 3 - Writer is drafting the report ...")
    print("=" * 50)

    research_combined: str = (
        f"SEARCH RESULTS : \n {state['search_results']} \n\n"
        f"DETAILED SCRAPED CONTENT : \n {state['scraped_content']}"
    )

    state["report"] = writer_chain.invoke(
        {"topic": topic, "research": research_combined}
    )

    print("\n Final Report\n", state["report"])

    # stage 4 - critic chain
    print("\n" + " =" * 50)
    print("step 4 - critic is reviewing the report ")
    print("=" * 50)

    state["feedback"] = critic_chain.invoke({"report": state["report"]})

    print("\n critic report \n", state["feedback"])

    return state

    return None
