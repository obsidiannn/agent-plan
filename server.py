# coding: utf-8

import uvicorn

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from server.config import CORS_ORIGINS
from server.core import auth
from server.routers import auth as auth_router, strategy as strategy_router, data as data_router, agent as agent_router

app = FastAPI(title="server")

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
app.include_router(strategy_router.router)
app.include_router(data_router.router)
app.include_router(agent_router.router)


@app.get("/")
def root():
    return {"data": "agent plan api is running"}


if __name__ == "__main__":
    # 启动应用，监听 8001 端口，0.0.0.0 表示监听所有网络接口
    uvicorn.run(app, host="0.0.0.0", port=8001)
