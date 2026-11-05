# coding: utf-8
"""中文金融情感/立场判定: FinBERT(yiyanghkust/finbert-tone-chinese)

在本地 CPU 上做 PyTorch 推理, 三分类结果映射为用户立场:
    Positive -> 积极, Negative -> 消极, Neutral -> 中性

模型约 400MB, 首次调用时从 HuggingFace 下载并缓存到 ~/.cache/finbert,
之后直接复用本地目录, 不再联网。
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import server.config  # noqa: F401  加载 server/.env(含代理配置)
from server.core.chroma_rag import configure_proxy

# 可用 STANCE_MODEL 环境变量换成其它同结构的中文分类模型
MODEL_REPO = os.environ.get("STANCE_MODEL", "yiyanghkust/finbert-tone-chinese")
MODEL_DIR = Path.home() / ".cache" / "finbert" / MODEL_REPO.split("/")[-1]
MAX_LENGTH = 512

# FinBERT 三分类标签 -> 用户立场
LABEL_TO_STANCE = {"Positive": "积极", "Negative": "消极", "Neutral": "中性"}


class FinBertStance:
    """FinBERT 中文情感分类器, 输出立场标签与三分类概率"""

    def __init__(self, batch_size: int = 16) -> None:
        import torch
        from huggingface_hub import snapshot_download
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
        )

        if not (MODEL_DIR / "config.json").exists():
            configure_proxy()  # 让 HF 下载走代理
            snapshot_download(repo_id=MODEL_REPO, local_dir=str(MODEL_DIR))

        self._torch = torch
        self._batch_size = batch_size
        self._tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
        self._model = AutoModelForSequenceClassification.from_pretrained(
            str(MODEL_DIR))
        self._model.eval()
        # 不同 transformers 版本下 id2label 的键可能是 int 或 str, 统一成 int
        self._id2label = {
            int(k): v for k, v in self._model.config.id2label.items()}

    def _classify_batch(self, texts: list[str]) -> list[dict]:
        torch = self._torch
        encoded = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=MAX_LENGTH,
            return_tensors="pt",
        )
        with torch.no_grad():
            logits = self._model(**encoded).logits
            probs = torch.softmax(logits, dim=-1).tolist()
        results = []
        for row in probs:
            scores = {
                self._id2label[i]: round(score, 4)
                for i, score in enumerate(row)
            }
            top = max(scores, key=scores.get)
            results.append({
                "stance": LABEL_TO_STANCE.get(top, top),
                "sentiment": scores,
            })
        return results

    def classify(self, texts: list[str]) -> list[dict]:
        """批量判定, 返回 [{"stance": 积极/消极/中性, "sentiment": {标签: 概率}}, ...]"""
        results: list[dict] = []
        for i in range(0, len(texts), self._batch_size):
            results.extend(self._classify_batch(texts[i:i + self._batch_size]))
        return results


_stance: FinBertStance | None = None
_lock = threading.Lock()


def get_stance() -> FinBertStance:
    """懒加载单例: 避免导入即下载/加载权重, 并发首次调用加锁串行化"""
    global _stance
    if _stance is None:
        with _lock:
            if _stance is None:
                _stance = FinBertStance()
    return _stance
