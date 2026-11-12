# coding: utf-8
"""Chroma 基础设施: 服务地址 / 中文 Embedding / 客户端与向量库工厂

RAG 文档问答、股吧舆情、MCP 工具共用这一层, 避免各处重复加载 ONNX 模型。
原来放在 core/chroma_rag.py, 拆分后由 chroma_rag(Agent 层)与
mcp/chroma_rag/service.py(能力层)共同依赖, 防止模块循环引用。
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import chromadb
import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings
from tokenizers import Tokenizer

import server.config  # noqa: F401  加载 server/.env

CHROMA_HOST = os.environ.get("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8000"))

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


_embeddings = None
_embeddings_lock = threading.Lock()


def get_embeddings() -> Embeddings:
    """进程内复用同一个 Embedding 实例, 避免反复加载 ONNX 模型"""
    global _embeddings
    if _embeddings is None:
        with _embeddings_lock:
            if _embeddings is None:
                configure_proxy()
                _embeddings = ChineseOnnxEmbeddings()
    return _embeddings


_client = None
_client_lock = threading.Lock()


def get_client() -> chromadb.ClientAPI:
    """Chroma HTTP 客户端(懒加载, 进程内复用)"""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                configure_proxy()
                _client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    return _client


_vectorstores: dict[str, Chroma] = {}
_vectorstores_lock = threading.Lock()


def get_vectorstore(collection_name: str) -> Chroma:
    """按集合名复用的 LangChain 向量库实例"""
    store = _vectorstores.get(collection_name)
    if store is None:
        with _vectorstores_lock:
            store = _vectorstores.get(collection_name)
            if store is None:
                store = Chroma(
                    collection_name=collection_name,
                    embedding_function=get_embeddings(),
                    client=get_client(),
                )
                _vectorstores[collection_name] = store
    return store
