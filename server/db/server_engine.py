# coding: utf-8
""" 库 (RBAC) 的 SQLAlchemy 引擎与会话

"""
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from server.config import (
    SERVER_DB_HOST,
    SERVER_DB_NAME,
    SERVER_DB_PASSWORD,
    SERVER_DB_PORT,
    SERVER_DB_USER,
)

url = (
    f"postgresql+psycopg2://{SERVER_DB_USER}:{SERVER_DB_PASSWORD}"
    f"@{SERVER_DB_HOST}:{SERVER_DB_PORT}/{SERVER_DB_NAME}"
)


engine = create_engine(
    url,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,
    echo=False,
)

SessionLocal = scoped_session(sessionmaker(bind=engine, expire_on_commit=False))
