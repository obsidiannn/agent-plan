# coding: utf-8
"""RAG 对话(LangChain + ChromaDB), 供路由 /api/agent/chroma 使用

由 demo/rag/chroma_rag.py 的命令行版本改造而来:
- 命令行 input() 循环  ->  FastAPI 路由 + SSE 流式响应
- 单进程列表存历史     ->  按 conversation_id 分桶的进程内历史(演示用)

流程: 文档切分 -> 向量化(Embedding) -> 写入 Chroma -> 相似度检索 -> LLM 流式作答
"""
from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path

import chromadb
import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from tokenizers import Tokenizer

import server.config  # noqa: F401  加载 server/.env

CHROMA_HOST = os.environ.get("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8000"))
COLLECTION_NAME = os.environ.get("RAG_COLLECTION", "rag-demo")
# 换知识库后置 RAG_REBUILD=true 重建一次索引; 之后保持 false 复用服务端集合
REBUILD = os.environ.get("RAG_REBUILD", "false").lower() == "true"
MAX_HISTORY = 20  # 单会话保留的最大消息条数, 超出丢弃最早的

RESOURCE_FILE = Path(__file__).resolve().parents[2] / "resource" / "三体.txt"

# 中文 Embedding: 本地 ONNX 版 bge-small-zh-v1.5(无需 API Key, 无需 torch)
EMBED_REPO = "Xenova/bge-small-zh-v1.5"
EMBED_DIR = Path.home() / ".cache" / "chroma" / \
    "onnx_models" / "bge-small-zh-v1.5"
EMBED_FILES = (
    "onnx/model.onnx",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "config.json",
)
EMBED_MAX_LENGTH = 512


def configure_proxy() -> None:
    """让 Chroma 下载 ONNX 模型时走代理。

    Chroma 的下载基于 httpx(trust_env=True), 会读取 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY;
    同时把 localhost 加入 NO_PROXY, 避免本地 Chroma Server 的请求被代理。
    """
    proxy = os.environ.get("RAG_PROXY") or os.environ.get("HTTPS_PROXY")
    if not proxy:
        return
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        os.environ.setdefault(key, proxy)
    no_proxy = os.environ.get("NO_PROXY", "")
    os.environ["NO_PROXY"] = ",".join(
        filter(None, [no_proxy, "localhost", "127.0.0.1"]))


def download_embed_model() -> None:
    """从 HuggingFace 拉取中文 ONNX 模型, 缺哪个文件补哪个(已缓存则跳过)。"""
    for name in EMBED_FILES:
        if (EMBED_DIR / name).exists():
            continue
        hf_hub_download(repo_id=EMBED_REPO, filename=name,
                        local_dir=str(EMBED_DIR))


class ChineseOnnxEmbeddings(Embeddings):
    """中文 ONNX Embedding 适配 LangChain 接口。

    模型: bge-small-zh-v1.5(ONNX 版), 走 onnxruntime CPU 推理;
    分词用 tokenizers 的 WordPiece; 池化方式与 BGE 一致: 取 [CLS] 向量再做 L2 归一化。
    """

    def __init__(self, batch_size: int = 16) -> None:
        download_embed_model()
        self._batch_size = batch_size
        self._tokenizer = Tokenizer.from_file(
            str(EMBED_DIR / "tokenizer.json"))
        self._tokenizer.enable_truncation(max_length=EMBED_MAX_LENGTH)
        # batch 内序列长度不一, 必须 padding 到等长才能拼成规整的 2D 张量
        self._tokenizer.enable_padding(
            pad_id=0, pad_token="[PAD]", pad_type_id=0)
        self._session = ort.InferenceSession(
            str(EMBED_DIR / "onnx" / "model.onnx"),
            providers=["CPUExecutionProvider"],
        )
        self._input_names = {i.name for i in self._session.get_inputs()}

    def _encode(self, texts: list[str]) -> list[list[float]]:
        encodings = self._tokenizer.encode_batch(texts)
        input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
        attention_mask = np.array(
            [e.attention_mask for e in encodings], dtype=np.int64)
        feed = {"input_ids": input_ids, "attention_mask": attention_mask}
        if "token_type_ids" in self._input_names:
            feed["token_type_ids"] = np.zeros_like(input_ids)
        last_hidden = self._session.run(None, feed)[0]
        cls = last_hidden[:, 0, :]
        norm = np.clip(np.linalg.norm(cls, axis=1, keepdims=True), 1e-12, None)
        return (cls / norm).tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            vectors.extend(self._encode(texts[i:i + self._batch_size]))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._encode([text])[0]


def build_embeddings() -> Embeddings:
    return ChineseOnnxEmbeddings()


def build_vectorstore(embeddings: Embeddings) -> Chroma:
    if not REBUILD:
        # 复用服务端已有集合, 避免每次启动都重复切分/灌库
        return Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            host=CHROMA_HOST,
            port=CHROMA_PORT,
        )
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:  # noqa: BLE001  集合不存在时忽略
        pass
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500, chunk_overlap=100)
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


_chain = None
_retriever = None
_init_lock = threading.Lock()

# 会话历史: {conversation_id: [HumanMessage/AIMessage, ...]}(进程内, 重启即清空)
_histories: dict[str, list] = {}


def get_chain():
    """懒加载: 首次调用才加载 ONNX 模型并连接 Chroma, 避免拖慢服务启动。

    并发首次调用时用锁串行初始化, 避免重复下载模型/重复灌库。
    """
    global _chain, _retriever
    if _chain is None:
        with _init_lock:
            if _chain is None:
                configure_proxy()
                _chain, _retriever = build_chain(build_embeddings())
    return _chain, _retriever


def _history(conversation_id: str) -> list:
    return _histories.setdefault(conversation_id, [])


async def astream_answer(conversation_id: str, question: str):
    """检索 -> 流式生成, 逐段 yield 文本; 生成结束后把本轮问答写回历史。

    检索是同步阻塞调用, 放到线程池执行, 避免阻塞 FastAPI 事件循环。
    """
    chain, retriever = get_chain()
    docs = await asyncio.to_thread(retriever.invoke, question)
    history = _history(conversation_id)

    answer = ""
    async for chunk in chain.astream({
        "context": format_docs(docs),
        "question": question,
        "history": history,
    }):
        if chunk:
            answer += chunk
            yield chunk

    history.append(HumanMessage(content=question))
    history.append(AIMessage(content=answer))
    del history[:-MAX_HISTORY]  # 只保留最近 MAX_HISTORY 条, 防止无限增长
