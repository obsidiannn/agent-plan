# coding: utf-8
"""RAG 知识库(Chroma)能力实现

所有已录入的文档共用一个集合(默认 rag-demo), 每条向量是文档的一个切片:
- document      切片正文
- metadata.source      文档名(唯一键, 同名上传会覆盖旧内容)
- metadata.chunk_index 切片序号(从 0 开始)
- metadata.uploaded_at 写入时间(ISO 字符串)

检索 / 文档清单 / 拆词导入在这里实现, 供 MCP 工具(server/mcp/chroma_rag/tools.py)
与对话 Agent(server/core/chroma_rag.py)共用。
"""
from __future__ import annotations

import os
import threading
from datetime import datetime
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from server.core.chroma_base import configure_proxy, get_client, get_vectorstore

# 集合名与旧版一致, 换知识库时可用 RAG_COLLECTION 覆盖
COLLECTION_NAME = os.environ.get("RAG_COLLECTION", "rag-demo")
# 首次启动/集合为空时导入的示例文档; RAG_REBUILD=true 会清空集合后重新导入
REBUILD = os.environ.get("RAG_REBUILD", "false").lower() == "true"
RESOURCE_FILE = Path(__file__).resolve().parents[3] / "resource" / "三体.txt"

TOP_K = 4          # 每次检索返回的切片数
FETCH_K = 20       # MMR 先取候选集大小, 兼顾相关性与多样性
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
UPSERT_BATCH = 500  # 单次写入 Chroma 的切片数(远小于服务端 5461 的上限)

_prepare_lock = threading.Lock()
_prepared = False


def _collection():
    """连接 Chroma Server 并取(或建)知识库集合"""
    configure_proxy()
    return get_client().get_or_create_collection(COLLECTION_NAME)


def _split(text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    return [chunk for chunk in splitter.split_text(text) if chunk.strip()]


def _write(vectorstore: Chroma, source: str, text: str) -> dict:
    """按 source 覆盖写入: 先删同名旧切片, 再追加新切片"""
    chunks = _split(text.replace("\r\n", "\n"))
    if not chunks:
        raise ValueError("文件内容为空, 没有可导入的文本")

    uploaded_at = datetime.now().isoformat(timespec="seconds")
    collection = _collection()
    # 同名文档视为更新: 清掉旧切片, 避免新旧内容同时被检索到
    try:
        collection.delete(where={"source": source})
    except Exception:  # noqa: BLE001  空集合/无匹配时忽略
        pass

    documents = [
        Document(
            page_content=chunk,
            metadata={
                "source": source,
                "chunk_index": index,
                "uploaded_at": uploaded_at,
            },
        )
        for index, chunk in enumerate(chunks)
    ]
    # Chroma 单次写入有批量上限(服务端默认 5461), 大文档按批写入更稳
    for start in range(0, len(documents), UPSERT_BATCH):
        batch = documents[start:start + UPSERT_BATCH]
        vectorstore.add_documents(
            batch,
            ids=[f"{source}#{start + offset}" for offset in range(len(batch))],
        )
    return {
        "source": source,
        "chunks": len(chunks),
        "chars": len(text),
        "uploaded_at": uploaded_at,
    }


def _ensure_seeded(vectorstore: Chroma) -> None:
    """集合为空时导入示例文档; RAG_REBUILD=true 时先清空再导入。

    只在首次连接时执行一次, 用户上传的文档不会因为普通启动被清掉。
    """
    global _prepared
    if _prepared:
        return
    with _prepare_lock:
        if _prepared:
            return
        collection = _collection()
        if REBUILD:
            ids = collection.get(include=[]).get("ids") or []
            if ids:
                collection.delete(ids=ids)
        if collection.count() == 0 and RESOURCE_FILE.exists():
            _write(vectorstore, RESOURCE_FILE.name,
                   RESOURCE_FILE.read_text(encoding="utf-8"))
        _prepared = True


def get_store() -> Chroma:
    vectorstore = get_vectorstore(COLLECTION_NAME)
    _ensure_seeded(vectorstore)
    return vectorstore


def list_documents() -> list[dict]:
    """已录入文档清单(按 source 聚合), 供前端侧边栏与 MCP 资源使用"""
    result = _collection().get(include=["metadatas", "documents"])
    metadatas = result.get("metadatas") or []
    documents = result.get("documents") or []

    merged: dict[str, dict] = {}
    for metadata, text in zip(metadatas, documents):
        metadata = metadata or {}
        source = metadata.get("source") or "未命名文档"
        item = merged.setdefault(source, {
            "source": source,
            "chunks": 0,
            "chars": 0,
            "uploaded_at": "",
        })
        item["chunks"] += 1
        item["chars"] += len(text or "")
        item["uploaded_at"] = max(
            item["uploaded_at"], metadata.get("uploaded_at") or "")

    return sorted(merged.values(),
                  key=lambda item: (item["uploaded_at"], item["source"]),
                  reverse=True)


def get_document_info(source: str) -> dict | None:
    """单篇文档的索引信息(切片数/字数/导入时间/开头预览)"""
    for item in list_documents():
        if item["source"] != source:
            continue
        result = _collection().get(
            where={"source": source}, include=["metadatas", "documents"])
        rows = list(zip(result.get("metadatas") or [],
                        result.get("documents") or []))
        rows.sort(key=lambda row: (row[0] or {}).get("chunk_index") or 0)
        preview = (rows[0][1] if rows else "") or ""
        return {**item, "preview": preview[:200]}
    return None


def ingest_text(source: str, text: str) -> dict:
    """把 txt 文本切分后写入 Chroma(上传接口与 MCP 导入工具共用)"""
    source = (source or "").strip()
    if not source:
        raise ValueError("文件名不能为空")
    if not text or not text.strip():
        raise ValueError("文件内容为空, 没有可导入的文本")
    return _write(get_store(), source, text)


def delete_document(source: str) -> dict:
    """删除某篇文档的全部切片"""
    collection = _collection()
    try:
        collection.delete(where={"source": source})
    except Exception:  # noqa: BLE001
        pass
    return {"source": source, "deleted": True}


def _retrieve(query: str, source: str | None) -> list[Document]:
    """MMR 检索: 选中某篇文档时只在该文档的切片内检索"""
    where = {"source": source} if source else None
    return get_store().max_marginal_relevance_search(
        query, k=TOP_K, fetch_k=FETCH_K, filter=where)


def _format_docs(docs: list[Document]) -> str:
    """把命中的切片拼成带来源标注的上下文"""
    blocks = []
    for doc in docs:
        metadata = doc.metadata or {}
        chunk_index = metadata.get("chunk_index")
        position = (f" | 第 {int(chunk_index) + 1} 段"
                    if chunk_index is not None else "")
        blocks.append(
            f"[来源: {metadata.get('source', '')}{position}]\n"
            f"{doc.page_content}"
        )
    return "\n\n".join(blocks)


def _sources(docs: list[Document]) -> list[dict]:
    """命中切片的摘要, 供前端标注引用来源

    旧版灌库的切片没有 chunk_index(整库只有一篇文档), 这里返回 None,
    前端只在字段存在时展示段落序号。
    """
    sources = []
    for doc in docs:
        metadata = doc.metadata or {}
        chunk_index = metadata.get("chunk_index")
        sources.append({
            "source": metadata.get("source", ""),
            "chunk_index": int(chunk_index) if chunk_index is not None else None,
            "snippet": doc.page_content[:120],
        })
    return sources


def search_answer(query: str, source: str | None = None) -> dict:
    """检索文档切片, 返回 {"document", "documents", "sources", "chunks", "text"}

    text 为交给模型的资料正文; sources 供前端展示(Agent 侧转成 SSE 事件)。
    source 不为空时只检索该篇文档, 为空则检索整个知识库。
    """
    available = list_documents()
    if not available:
        return {
            "document": source or "",
            "documents": [],
            "sources": [],
            "total_chunks": 0,
            "text": "知识库暂无已录入的文档, 请先在侧边栏上传 txt 文件。",
        }

    if source and source not in {item["source"] for item in available}:
        return {
            "document": source,
            "documents": available,
            "sources": [],
            "total_chunks": 0,
            "text": f"知识库中没有名为《{source}》的文档, 可先上传, 或改用其他文档提问。",
        }

    docs = _retrieve(query, source)
    if not docs:
        return {
            "document": source or "",
            "documents": available,
            "sources": [],
            "total_chunks": 0,
            "text": "没有检索到与该问题相关的内容。",
        }

    scope = f"当前限定文档: {source}" if source else "当前范围: 全部文档"
    return {
        "document": source or "",
        "documents": available,
        "sources": _sources(docs),
        "total_chunks": sum(item["chunks"] for item in available),
        "text": f"{scope}\n\n资料:\n{_format_docs(docs)}",
    }
