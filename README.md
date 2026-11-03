uvicorn main:app --reload --port 8001
uvicorn main:app --reload --port 8001

uv add "langgraph-cli[inmem]"
langgraph dev  


```shell
pip install "psycopg[binary]"

# 生成表结构
  sqlacodegen postgresql+psycopg://postgres:postgres@localhost:6888/agent_plan --outfile=structure-pg.py 
```