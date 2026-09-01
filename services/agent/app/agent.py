from langchain.agents import create_agent

from app.llm import get_chat_client
from app.tools.knowledge_base import search_knowledge_base


SYSTEM_PROMPT = (
    "知识库相关问题先调用 search_knowledge_base 获取依据，再基于工具结果回答；"
    "通用问题直接回答，不要无依据调用工具。"
)

agent = create_agent(
    get_chat_client(),
    tools=[search_knowledge_base],
    system_prompt=SYSTEM_PROMPT,
)
