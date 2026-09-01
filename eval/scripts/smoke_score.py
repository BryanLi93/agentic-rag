import os
from dotenv import load_dotenv
from pydantic import SecretStr
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.callbacks import BaseCallbackHandler

from ragas import RunConfig
from ragas import SingleTurnSample, EvaluationDataset, evaluate
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    Faithfulness,
    LLMContextRecall,
    LLMContextPrecisionWithReference,
    ResponseRelevancy
)
from ragas.embeddings import LangchainEmbeddingsWrapper

load_dotenv()

class ShowLLM(BaseCallbackHandler):
    n = 0
    def on_llm_end(self, response, **kwargs):       # 裁判每调一次 LLM,这里就被触发
        for gens in response.generations:
            for g in gens:
                ShowLLM.n += 1
                print(f"\n===== 第 {ShowLLM.n} 次 LLM 输出 =====")
                print(g.text)

judge = ChatOpenAI(
    model=os.environ["CHAT_MODEL"],
    api_key=SecretStr(os.environ["OPENAI_API_KEY"]),
    base_url=os.environ["OPENAI_BASE_URL"],
    # callbacks=[ShowLLM()],
    extra_body={"enable_thinking": False},   # 关思考,让裁判直接给结构化结论
)
judge = LangchainLLMWrapper(judge)

emb = OpenAIEmbeddings(
    model=os.environ["EMBEDDING_MODEL"],                # bge-m3
    api_key=SecretStr(os.environ["OPENAI_API_KEY"]),
    base_url=os.environ["OPENAI_BASE_URL"],
    check_embedding_ctx_length=False, # OpenAIEmbeddings 默认会用 tiktoken 先把文字切成 token、按 OpenAI 模型的规矩发token 编号数组。这是"OpenAI 兼容接口接非 OpenAI embedding 模型"的通用坑。
)
emb = LangchainEmbeddingsWrapper(emb)

sample = SingleTurnSample(
    # 聚焦单一主题:只问 chunk_overlap 一件事(不再一题问俩参数)
    user_input="chunk_overlap 在 RAG 文档切分里起什么作用?",
    # 两段都讲 chunk_overlap、都直接支撑标准答案 → precision 判每段都"够" → 应接近 1.0
    retrieved_contexts=[
        "chunk_overlap 指相邻文本块之间的重叠长度。设置重叠是为了防止一句完整的话在切分时被从中间截断,导致上下文丢失。",
        "让相邻块保留一部分重复内容,可以保证跨块语义连续,检索时不会因为切断而丢失关键信息。",
    ],
    # 答案完全基于上面两段、没有编造 → faithfulness 也应该高
    response=(
        "chunk_overlap 是相邻文本块之间的重叠部分,"
        "作用是防止句子在切分边界被截断,从而保证上下文连续、检索时不丢失关键信息。"
        "chunk_size 指每个文本块的最大长度。chunk_size 太大,单个块塞入过多内容,检索时定位精度会下降,容易召回不相关的信息。"
    ),
    # 标准答案也只聚焦 chunk_overlap 这一件事,粒度和检索片段对齐
    reference=(
        "chunk_overlap 是相邻文本块之间的重叠部分,作用是防止一句完整的话在切分时"
        "被从中间截断,保留跨块的上下文连续性,避免检索时丢失关键信息。"
    ),
)

dataset = EvaluationDataset(samples=[sample])
result = evaluate(
    dataset,
    metrics=[
        Faithfulness(),
        LLMContextRecall(),
        LLMContextPrecisionWithReference(),
        ResponseRelevancy(),
    ],
    llm=judge,
    embeddings=emb,
    run_config=RunConfig(max_workers=1, timeout=600),
)
print(result)
