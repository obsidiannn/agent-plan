# coding: utf-8

import uvicorn

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from server.config import CORS_ORIGINS
from server.core import auth
from server.db.agent_checkpoint import init_agent_checkpoint_tables
from server.routers import auth as auth_router, agent as agent_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时确保 LangGraph 检查点表存在(幂等), 供人工审批工作流落库
    init_agent_checkpoint_tables()
    yield


app = FastAPI(title="server", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(auth.ApiError)
def handle_api_error(request: Request, exc: auth.ApiError):
    return JSONResponse(status_code=exc.status_code, content=exc.payload)


app.include_router(auth_router.router)
app.include_router(agent_router.router)


@app.get("/")
def root():
    return {"data": "agent plan api is running"}


if __name__ == "__main__":
    # 启动应用，监听 8001 端口，0.0.0.0 表示监听所有网络接口
    uvicorn.run(app, host="0.0.0.0", port=8001)
