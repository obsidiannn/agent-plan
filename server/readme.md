
* pip install fastapi uvicorn psycopg2-binary

```shell
# 本地执行
venv/bin/uvicorn stocking_runner:app --reload --port 8000

# 后台执行
nohup venv/bin/uvicorn  stocking_runner:app --host 0.0.0.0 --port 8000 > uvicorn.log 2>&1 &
nohup uvicorn  stocking_runner:app --host 0.0.0.0 --port 8000 > uvicorn.log 2>&1 &
```