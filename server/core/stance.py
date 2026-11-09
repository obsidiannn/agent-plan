# coding: utf-8
"""中文金融情感/立场判定: FinBERT(yiyanghkust/finbert-tone-chinese)

在本地 CPU 上做 PyTorch 推理, 三分类结果映射为用户立场:
    Positive -> 积极, Negative -> 消极, Neutral -> 中性

针对股吧语料(散户口语/短标题)做了三层补偿:
    1. 输入拼接: 标题 + 正文, 并去掉 $股票标记$ / 链接 / @ 等噪声
    2. 强信号词典: 命中高精度词(涨停/割肉...)时按净票数覆盖模型结果
    3. 置信度阈值: 模型自身也没把握时统一落在中性, 不硬判

模型约 400MB, 首次调用时从 HuggingFace 下载并缓存到 ~/.cache/finbert,
之后直接复用本地目录, 不再联网。
"""
from __future__ import annotations

import os
import re
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

# 统一的立场标签集合(也是评测认得的合法标注)
STANCES = ("积极", "消极", "中性")

# 模型置信度低于该值时不再硬判, 统一落在中性上
MIN_CONFIDENCE = float(os.environ.get("STANCE_MIN_CONFIDENCE", "0.6"))

# 股吧高频强信号词: 命中即按净票数覆盖模型结果(高精度, 用于修正明显误判)
POSITIVE_WORDS = (
    "涨停", "起飞", "满仓", "抄底", "加仓", "翻倍", "利好", "牛市",
    "创新高", "突破", "大涨", "拉升", "梭哈", "站稳",
)
NEGATIVE_WORDS = (
    "跌停", "割肉", "垃圾", "退市", "跑路", "套牢", "腰斩", "崩盘",
    "利空", "熊市", "闷杀", "被套", "大跌", "暴跌", "退钱",
)

# 股吧正文里的噪声: $股票名(SZ代码)$ 标记 / 链接 / @昵称
_NOISE_PATTERNS = (
    re.compile(r"\$[^$\n]{1,40}\$"),
    re.compile(r"https?://\S+"),
    re.compile(r"@[\w\-.]+"),
)


def clean_text(raw: str) -> str:
    """去掉股吧正文里的代码标记/链接/@ 等噪声, 只留下可用于判定的语句"""
    text = raw or ""
    for pattern in _NOISE_PATTERNS:
        text = pattern.sub(" ", text)
    return " ".join(text.split())


def build_text(title: str = "", content: str = "") -> str:
    """拼出送模型的文本: 标题在前(信息密度高且必填), 正文在后补充语境

    股吧标题常是"见鬼""一群"这类无观点短句, 单靠标题无法判定, 必须带上正文。
    """
    parts = [t for t in (clean_text(title), clean_text(content)) if t]
    return "。".join(parts)


def lexicon_stance(text: str) -> str | None:
    """高精度强信号词典: 正负持平或无命中时返回 None, 交回给模型判断"""
    pos = sum(text.count(word) for word in POSITIVE_WORDS)
    neg = sum(text.count(word) for word in NEGATIVE_WORDS)
    if pos > neg:
        return "积极"
    if neg > pos:
        return "消极"
    return None


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
        for text, row in zip(texts, probs):
            scores = {
                self._id2label[i]: round(score, 4)
                for i, score in enumerate(row)
            }
            top = max(scores, key=scores.get)
            # 1) 强信号词典优先: 命中高精度词时直接采信, 修正模型的明显误判
            stance = lexicon_stance(text)
            if stance is None:
                # 2) 无强信号时用模型, 但模型自身也没把握就不硬判
                stance = (LABEL_TO_STANCE.get(top, top)
                          if scores[top] >= MIN_CONFIDENCE else "中性")
            results.append({"stance": stance, "sentiment": scores})
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
