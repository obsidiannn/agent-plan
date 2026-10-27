# coding: utf-8
"""请求体 Pydantic 模型"""
from typing import List, Optional

from pydantic import BaseModel, Field
from typing import Optional, Literal

class LoginRequest(BaseModel):
    username: str = ""
    password: str = ""


class DayKlineRequest(BaseModel):
    stockCode: str
    date: str
    offset: int = 0
    market: str


class Min5KlineRequest(BaseModel):
    stockCode: str
    start: str
    end: str
    offset: int = 0
    market: str


class IndicatorRequest(BaseModel):
    # 兼容多种字段命名 (indicator_type/indicatorType 等)
    indicator_type: Optional[str] = None
    indicatorType: Optional[str] = None
    starttime: Optional[int] = None
    startTime: Optional[int] = None
    start_time: Optional[int] = None
    endtime: Optional[int] = None
    endTime: Optional[int] = None
    end_time: Optional[int] = None


class StrategyConfirmRequest(BaseModel):
    dataIdx: str
    strategyCode: str


class StrategyRecordsRequest(BaseModel):
    strategy: str = ""
    date: str = ""
    excludes: List[str] = []


class SnapshotRecordsRequest(BaseModel):
    level: str = ""
    date: str = ""


class UserRecordRequest(BaseModel):
    strategy: str = ""
    date: str = ""


class StockIndexItem(BaseModel):
    market_code: str = ""
    index_code: str = ""
    index_name: str = ""




class AnalyzeRequest(BaseModel):
    # ---- 会话与追踪 ----
    request_id: Optional[str] = Field(None, description="本次请求唯一 ID，原样回传在 SSE 事件里，便于前端对账")
    conversation_id: Optional[str] = Field(None, description="多轮会话 ID；首次不传，后端生成后在首个事件里返回。映射到 LangGraph thread_id")

    # ---- 核心三元组 ----
    prompt: str =  Field(..., description="用户额外的问题描述")
    ticker: str = Field(..., description="股票代码，如 600519 / 600519.SH / 00700.HK / AAPL")
    market: Literal["sz","sh"] = Field("sh", description="市场，用于解析 ticker 与选择数据源")
    buy_time: str = Field(
        ...,
        description="买入时点；None 表示当前。带时区，或按交易所本地时区解释为当日收盘"
    )

    strategy_type: str = Field(..., min_length=1, description="策略类型；若命中策略清单则用清单内 type，否则自定义标识")

    # ---- 可选约束（对应 prompt 优先级堆栈第 3 层）----
    horizon: Optional[Literal["short", "medium", "long"]] = None
    risk_preference: Optional[Literal["conservative", "balanced", "aggressive"]] = None

    # ---- 可选覆盖项 ----
    index_universe_override: Optional[list[str]] = Field(
        None, description="指定参与分析的指数代码；不传则用服务端默认清单"
    )
    window_hint: Optional[Literal["1d"]] = Field(
        None, description="策略适配性评估所用窗口；不传由 Agent 自行声明"
    )
