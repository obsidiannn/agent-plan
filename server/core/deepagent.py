# 文件路径：hello_agent.py

import os
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_openai import ChatOpenAI
from server.services import kline_service
from server.schemas.requests import StockIndexItem
from server.hikyuu_init import * 

# 使用 ChatOpenAI 并将 base_url 指向 DeepSeek，这是最直接的接入方式
model = ChatOpenAI(
    model="deepseek-flash",          
    api_key=os.environ["OPENAI_API_KEY"],  
    base_url=os.environ["OPENAI_BASE_URL"],   
)


def get_stock_indices(market: str, ticker: str) -> list[StockIndexItem]:
    """
        获取股票指数列表
        request: market = sz或者sh, ticker = 股票代码,类似 000034
        return:{
            market_code: 'sz'或'sh' 
            index_code: '000001'
            index_name: '上证指数',
        }
    """

    stock_code = market + ticker
    stock = sm[stock_code]
    list = []

    if blocka and blocka[stock_code].code == stock.code:
        bk = blocka.index_stock
        list.append(StockIndexItem(market_code=bk.market,index_code=bk.code,index_name=bk.name))

    if blocksz and blocksz[stock_code].code == stock.code:
        bk = blocksz.index_stock
        list.append(StockIndexItem(market_code=bk.market,index_code=bk.code,index_name=bk.name))

    # https://hikyuu.readthedocs.io/zh-cn/latest/base/constant.html
    if blockzxb and blockzxb[stock_code].code == stock.code:
        bk = blockzxb.index_stock
        list.append(StockIndexItem(market_code=bk.market,index_code=bk.code,index_name=bk.name))

    # if blockg and blockg[stock_code].code == stock.code:
    #     bk = blockg.index_stock
    #     list.append(StockIndexItem(market_code=bk.market,index_code=bk.code,index_name=bk.name))

    if zsbk_sh50 and zsbk_sh50[stock_code].code == stock.code:
        bk = zsbk_sh50.index_stock
        list.append(StockIndexItem(market_code=bk.market,index_code=bk.code,index_name=bk.name))

    if zsbk_sh180 and zsbk_sh180[stock_code].code == stock.code:
        bk = zsbk_sh180.index_stock
        list.append(StockIndexItem(market_code=bk.market,index_code=bk.code,index_name=bk.name))

    if zsbk_hs300 and zsbk_hs300[stock_code].code == stock.code:
        bk = zsbk_hs300.index_stock
        list.append(StockIndexItem(market_code=bk.market,index_code=bk.code,index_name=bk.name))

    if zsbk_zz100 and zsbk_zz100[stock_code].code == stock.code:
        bk = zsbk_zz100.index_stock 
        list.append(StockIndexItem(market_code=bk.market,index_code=bk.code,index_name=bk.name))

    return list


def query_kline_day(market: str, code: str, strategy_date: str):
    """
        查询日k线 数组 
        market: 'sz'或'sh' 
        code: 股票代码,如 '000034'
        strategy_date: 策略日期, 如 '20260101'
    """
    list = kline_service.query_day_kline(market, code, strategy_date )
    if not list:
        return []
    return [k for k in list if int(k["date"]) < int(strategy_date)]

def query_kline_week(market: str, code: str,  strategy_date: str):
    """
        查询周k线 数组
        market: 'sz'或'sh' 
        code: 股票代码,如 '000034'
        strategy_date: 策略日期, 如 '20260101'
    """
    list = kline_service.query_week_kline(market, code, strategy_date)
    if not list:
        return []
    return [k for k in list if int(k["date"]) < int(strategy_date)]

def query_index_day(market: str, code: str,  strategy_date: str):
    """
        查询日k线 指数
        market: 'sz'或'sh' 
        code: 股票代码,如 '000001'
        strategy_date: 策略日期, 如 '20260101'
    """
    list = kline_service.query_day_kline(market, code, strategy_date)
    if not list:
        return []
    return [k for k in list if int(k["date"]) < int(strategy_date)]

def query_index_week(market: str, code: str,  strategy_date: str):
    """
        查询周k线 指数
        market: 'sz'或'sh' 
        code: 股票代码,如 '000001'
        strategy_date: 策略日期, 如 '20260101'
    """
    list = kline_service.query_week_kline(market, code, strategy_date)
    if not list:
        return []
    return [k for k in list if int(k["date"]) < int(strategy_date)]


# 项目根目录下的 resource 作为 agent 的虚拟文件系统根目录 (deepagent.py -> core -> server -> 项目根)
RESOURCE_DIR = Path(__file__).resolve().parents[2] / "resource"

# 系统提示词取自项目根目录 doc/promot.md
PROMPT_FILE = Path(__file__).resolve().parents[2] / "doc" / "promot.md"

agent = create_deep_agent(
    model=model,
    tools=[query_kline_day, query_kline_week, query_index_day, query_index_week,get_stock_indices ],
    backend=FilesystemBackend(root_dir=RESOURCE_DIR, virtual_mode=True),
    # memory 是文件路径列表(AGENTS.md), 虚拟路径 /memory/AGENTS.md 即 resource/memory/AGENTS.md
    memory=["/memory/AGENTS.md"],
    system_prompt=PROMPT_FILE.read_text(encoding="utf-8"),
)
