from typing import Annotated

from dotenv import load_dotenv
from langchain_core.messages import AnyMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from .rag_store import retrieve_context_for_session

load_dotenv()


class GraphState(BaseModel):
    messages: Annotated[list[AnyMessage], add_messages] = Field(default_factory=list)


llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0,
)


def chatbot(
    state: GraphState, config: RunnableConfig | None = None
) -> dict[str, list[AnyMessage]]:
    messages = state.messages
    latest_user_message = messages[-1].content if messages else ""
    if not isinstance(latest_user_message, str):
        latest_user_message = str(latest_user_message)

    configurable = config.get("configurable", {}) if config else {}
    thread_id = configurable.get("thread_id")
    session_id = thread_id if isinstance(thread_id, str) else ""

    # Retrieve PDF context specific to this session
    context = (
        retrieve_context_for_session(latest_user_message, session_id)
        if session_id
        else ""
    )

    system_prompt = SystemMessage(
        content=(
            "You are a helpful AI assistant. Answer user questions based on the "
            "provided document context if available.\n\n"
            f"--- Document Context ---\n{context if context else 'No document attached.'}\n------------------------"
        )
    )

    response = llm.invoke([system_prompt] + messages)
    return {"messages": [response]}


builder = StateGraph(GraphState)
builder.add_node("chatbot", chatbot)
builder.add_edge(START, "chatbot")

graph = builder.compile(checkpointer=InMemorySaver())
