
# coding: utf-8
"""LangChain + ChromaDB 的 RAG 命令行对话(知识库: resource/三体.txt)

流程: 文档切分 -> 向量化(Embedding) -> 写入 Chroma -> 相似度检索 -> LLM 基于检索结果作答

    uv run python demo/rag/chroma_rag.py
"""
import os
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from ragas import EvaluationDataset, evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import AnswerRelevancy, Faithfulness


CHROMA_HOST = os.environ.get("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8000"))
COLLECTION_NAME = "rag-demo"
REBUILD = True  # 换知识库后需重建一次索引; 之后可改为 False 复用服务端集合
EVAL_ENABLED = True  # 每轮回答后是否用 ragas 即时打分(可用 /eval 命令切换)

RESOURCE_FILE = Path(__file__).resolve().parents[2] / "resource" / "三体.txt"


class ChromaLocalEmbeddings(Embeddings):
    """把 Chroma 自带的本地 ONNX 模型(MiniLM)适配成 LangChain 的 Embeddings 接口。

    无需任何 API Key / 外部服务, 模型已缓存在 ~/.cache/chroma/onnx_models
    """

    def __init__(self) -> None:
        self._fn = DefaultEmbeddingFunction()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, vec)) for vec in self._fn(texts)]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def build_embeddings() -> Embeddings:
    return ChromaLocalEmbeddings()


def build_vectorstore(embeddings: Embeddings) -> Chroma:
    if REBUILD:
        client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:  # noqa: BLE001  集合不存在时忽略
            pass
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
    chunks = splitter.split_documents(
        [Document(
            page_content=RESOURCE_FILE.read_text(encoding="utf-8"),
            metadata={"source": RESOURCE_FILE.name},
        )]
    )
    return Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        host=CHROMA_HOST,
        port=CHROMA_PORT,
    )


def format_docs(docs: list[Document]) -> str:
    return "\n\n".join(doc.page_content for doc in docs)


def build_chain(embeddings: Embeddings):
    vectorstore = build_vectorstore(embeddings)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

    llm = ChatOpenAI(
        model="deepseek-flash",
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ["OPENAI_BASE_URL"],
        max_tokens=1024,
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "你是《三体》小说的问答助手。只能依据下面资料回答, 资料中没有的信息要明确说不知道。\n\n"
         "资料:\n{context}"),
        MessagesPlaceholder("history"),
        ("human", "{question}"),
    ])

    answer_chain = prompt | llm | StrOutputParser()
    return answer_chain, retriever


def build_judge() -> tuple:
    """ragas 的评委: LLM 判 Faithfulness, Embedding 判 AnswerRelevancy"""
    llm = ChatOpenAI(
        model="deepseek-flash",
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ["OPENAI_BASE_URL"],
        max_tokens=1024,
    )
    return LangchainLLMWrapper(llm), LangchainEmbeddingsWrapper(build_embeddings())


def score_answer(question: str, answer: str, contexts: list[str],
                 judge_llm, judge_embeddings) -> dict:
    """对单轮问答即时打分, 返回 {指标名: 分数}"""
    dataset = EvaluationDataset.from_list([{
        "user_input": question,
        "response": answer,
        "retrieved_contexts": contexts,
    }])
    result = evaluate(
        dataset=dataset,
        metrics=[Faithfulness(), AnswerRelevancy()],
        llm=judge_llm,
        embeddings=judge_embeddings,
    )
    return result.scores[0]


def main() -> None:
    embeddings = build_embeddings()
    answer_chain, retriever = build_chain(embeddings)
    judge_llm, judge_embeddings = build_judge()
    history: list = []
    eval_on = EVAL_ENABLED

    print("exit/quit 退出, /clear 清空历史, /eval 开关评测")
    while True:
        try:
            user_input = input("you: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break
        if user_input == "/clear":
            history.clear()
            print("已清空会话历史")
            continue
        if user_input == "/eval":
            eval_on = not eval_on
            print(f"评测已{'开启' if eval_on else '关闭'}")
            continue
        try:
            docs = retriever.invoke(user_input)
            answer = answer_chain.invoke({
                "context": format_docs(docs),
                "question": user_input,
                "history": history,
            })
        except Exception as exc:  # noqa: BLE001
            print(f"请求出错: {exc}")
            continue
        history.append(HumanMessage(content=user_input))
        history.append(AIMessage(content=answer))
        print(f"AI: {answer}")
        if eval_on:
            try:
                scores = score_answer(
                    user_input, answer, [d.page_content for d in docs],
                    judge_llm, judge_embeddings,
                )
                print("[评测] " + ", ".join(
                    f"{k}={v:.3f}" for k, v in scores.items()))
            except Exception as exc:  # noqa: BLE001
                print(f"[评测失败] {exc}")


if __name__ == "__main__":
    main()
