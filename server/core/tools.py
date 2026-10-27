# coding: utf-8

from server.schemas.requests import StockIndexItem
from server.services import kline_service
from server.hikyuu_init import *


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
