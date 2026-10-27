# coding: utf-8
"""stocking 应用配置: 从 .env 读取, 兼容 k-training 的环境变量命名"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    # python-dotenv 未安装时, 手动解析 .env
    _env_file = Path(__file__).resolve().parent / ".env"
    if _env_file.exists():
        for _line in _env_file.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _, _v = _line.partition("=")
            _v = _v.strip().strip('"').strip("'")
            os.environ.setdefault(_k.strip(), _v)

# JWT
JWT_SECRET = os.getenv("JWT_SECRET", os.getenv("JWT_SECRET", ""))
JWT_EXPIRES_DAYS = 7
AUTH_COOKIE = "k_token"


# stocking 库 (用户/角色/权限 RBAC)
SERVER_DB_HOST = os.getenv("SERVER_DB_HOST", "127.0.0.1")
SERVER_DB_PORT = int(os.getenv("SERVER_DB_PORT", "6888"))
SERVER_DB_NAME = os.getenv("SERVER_DB_NAME", "stocking")
SERVER_DB_USER = os.getenv("SERVER_DB_USER", "root")
SERVER_DB_PASSWORD = os.getenv("SERVER_DB_PASSWORD", "888888")

# CORS 允许的前端来源, 逗号分隔
CORS_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()
]
