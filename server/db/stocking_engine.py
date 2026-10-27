# coding: utf-8
"""stocking 库 (RBAC) 的 SQLAlchemy 引擎与会话

与 hikyuu_analysis 库独立, 对应 k-training 的 stockingPrisma
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from server.config import (
    STOCKING_DB_HOST,
    STOCKING_DB_NAME,
    STOCKING_DB_PASSWORD,
    STOCKING_DB_PORT,
    STOCKING_DB_USER,
)

url = (
    f"postgresql+psycopg2://{STOCKING_DB_USER}:{STOCKING_DB_PASSWORD}"
    f"@{STOCKING_DB_HOST}:{STOCKING_DB_PORT}/{STOCKING_DB_NAME}"
)
# url = (
#     f"mysql+pymysql://{STOCKING_DB_USER}:{STOCKING_DB_PASSWORD}"
#     f"@{STOCKING_DB_HOST}:{STOCKING_DB_PORT}/{STOCKING_DB_NAME}?charset=utf8mb4"
# )

engine = create_engine(
    url,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,
    echo=False,
)

SessionLocal = scoped_session(sessionmaker(bind=engine, expire_on_commit=False))
