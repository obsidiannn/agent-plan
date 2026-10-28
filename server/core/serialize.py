# coding: utf-8
"""SQLAlchemy 模型 / Decimal / datetime 的 JSON 序列化

- Decimal -> float
- datetime/date -> isoformat
- BIT(1) bytes -> bool
"""
import datetime
from decimal import Decimal


def serialize(obj):
    if obj is None:
        return None
    if isinstance(obj, (list, tuple)):
        return [serialize(o) for o in obj]
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, (bytes, bytearray)):
        # 兼容驱动返回 bytes 的情况（如 BIT 类型）
         # pymysql 的 BIT(1) 返回 bytes
        try:
            return bool(int.from_bytes(obj, "little"))
        except Exception:
            return None
    if isinstance(obj, bool):
        return obj
    if hasattr(obj, "__table__"):
        result = {}
        for col in obj.__table__.columns:
            result[col.name] = serialize(getattr(obj, col.name))
        return result
    return obj
