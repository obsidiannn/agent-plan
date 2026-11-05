# coding: utf-8
"""东方财富股吧列表爬虫

数据来源: claw_task(任务表) + clas_task_detail(任务明细表)
最终抓取地址 = base_url % claw_param
"""
import json
import random
import subprocess
import sys
from pathlib import Path

import scrapy
from scrapy import signals
from scrapy.crawler import CrawlerProcess
from sqlalchemy import func

from server.core.logs import logger
from server.db.server_engine import SessionLocal
from server.db.server_models import ClasTaskDetail, ClawTask

PROJECT_ROOT = Path(__file__).resolve().parents[2]
base_url = "https://guba.eastmoney.com/list,%s.html"
detail_url = "https://guba.eastmoney.com/news,002777,1792015179.html"

# 会话入口: 先访问首页建立 Cookie 会话, 再抓列表页
HOME_URL = "https://guba.eastmoney.com/"

# 浏览器指纹档案(UA 与其配套的 sec-ch-ua 字段必须一致), 每次会话固定其一
UA_PROFILES = (
    {
        "ua": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "brands": ('"Chromium";v="124", "Google Chrome";v="124", '
                   '"Not-A.Brand";v="99"'),
        "platform": '"macOS"',
    },
    {
        "ua": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        "brands": ('"Chromium";v="125", "Google Chrome";v="125", '
                   '"Not-A.Brand";v="99"'),
        "platform": '"Windows"',
    },
)

# 补齐真实浏览器会带的请求头, 避免因指纹缺失被风控
BROWSER_HEADERS = {
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "keep-alive",
}


def load_targets() -> list[dict]:
    """读取激活任务及其明细参数, 拼接出待抓取地址"""
    session = SessionLocal()
    try:
        rows = (
            session.query(ClawTask, ClasTaskDetail)
            .join(ClasTaskDetail, ClasTaskDetail.task_id == ClawTask.id)
            .filter(ClawTask.active.is_(True))
            .all()
        )
        targets = []
        for task, detail in rows:
            if not detail.claw_param:
                logger.warning(f"跳过缺少 claw_param 的明细, task_id={task.id}")
                continue
            targets.append(
                {
                    "task_code": task.task_code,
                    "task_name": task.task_name,
                    "claw_param": detail.claw_param,
                    "url": base_url % detail.claw_param,
                }
            )
        logger.info(f"共加载 {len(targets)} 个抓取目标")
        return targets
    finally:
        SessionLocal.remove()


def ensure_target(claw_param: str) -> dict:
    """确保该参数已存在于 clas_task_detail, 不存在就挂到激活任务下新建一条

    返回结构同 load_targets 的元素, 可直接交给采集器使用。
    """
    session = SessionLocal()
    try:
        task = session.query(ClawTask).filter(
            ClawTask.active.is_(True)).first()
        if task is None:
            raise ValueError("没有激活的采集任务, 无法新建参数明细")
        detail = (
            session.query(ClasTaskDetail)
            .filter(ClasTaskDetail.claw_param == claw_param)
            .first()
        )
        if detail is None:
            # 该表由手工 DDL 创建, id 无自增序列, 需要自己取下一个值
            next_id = (session.query(
                func.max(ClasTaskDetail.id)).scalar() or 0) + 1
            session.add(ClasTaskDetail(
                id=next_id, task_id=task.id, claw_param=claw_param))
            session.commit()
            logger.info(
                f"新建采集明细: id={next_id}, task_id={task.id}, claw_param={claw_param}")
        return {
            "task_code": task.task_code,
            "task_name": task.task_name,
            "claw_param": claw_param,
            "url": base_url % claw_param,
        }
    finally:
        SessionLocal.remove()


class GubaListSpider(scrapy.Spider):
    """按库中任务配置抓取股吧列表页"""

    name = "guba_list"
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        # 保守频率: 基础间隔 6s 上下浮动 50%, 单域并发 1
        "DOWNLOAD_DELAY": 6,
        "DOWNLOAD_DELAY_JITTER": 0.5,
        "CONCURRENT_REQUESTS": 1,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "COOKIES_ENABLED": True,
    }

    def __init__(self, targets: list[dict] | None = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 未显式传入目标时, 回退到从库里读取
        self.targets = targets if targets is not None else load_targets()
        # 整个会话固定一套浏览器指纹, 避免 UA 频繁跳变反而更可疑
        self.profile = random.choice(UA_PROFILES)

    def _headers(self, referer: str | None = None) -> dict:
        headers = dict(BROWSER_HEADERS)
        headers["User-Agent"] = self.profile["ua"]
        headers["sec-ch-ua"] = self.profile["brands"]
        headers["sec-ch-ua-mobile"] = "?0"
        headers["sec-ch-ua-platform"] = self.profile["platform"]
        if referer:
            headers["Referer"] = referer
        return headers

    def _request(self, url, callback, meta=None, referer=None, errback=None):
        return scrapy.Request(
            url,
            callback=callback,
            errback=errback,
            meta=meta or {},
            headers=self._headers(referer),
            dont_filter=True,
        )

    async def start(self):
        # 先走一次首页建立 Cookie 会话, 再按目标抓列表页
        yield self._request(HOME_URL, self.parse_home)

    def parse_home(self, response):
        if not response.text:
            logger.warning("股吧首页未返回内容, 会话可能未建立")
        for target in self.targets:
            yield self._request(
                target["url"],
                self.parse_list,
                meta={"target": target},
                referer=HOME_URL,
            )

    def parse_list(self, response):
        target = response.meta["target"]
        for row in response.css("tr.listitem"):
            link = row.css("div.title a")
            if not link:
                continue
            item = {
                "task_code": target["task_code"],
                "task_name": target["task_name"],
                "claw_param": target["claw_param"],
                "title": link.attrib.get("title") or link.css("::text").get("").strip(),
                "url": response.urljoin(link.attrib.get("href", "")),
                "author": row.css("div.author a::text").get("").strip(),
                "read_count": row.css("div.read::text").get("").strip(),
                "comment_count": row.css("div.reply::text").get("").strip(),
                "publish_time": row.css("div.update::text").get("").strip(),
                "content": "",
            }
            # 列表页只有摘要, 继续跟进详情页抓取正文
            yield self._request(
                item["url"],
                self.parse_detail,
                meta={"item": item},
                referer=response.url,
                errback=self.detail_failed,
            )

    def parse_detail(self, response):
        item = response.meta["item"]
        text = response.css("div.newstext div.xeditor_content").xpath(
            "string(.)").get() or ""
        item["content"] = " ".join(text.split())
        yield item

    def detail_failed(self, failure):
        """详情页抓取失败时, 退化为仅保留列表页字段, 避免整条数据丢失"""
        item = failure.request.meta["item"]
        logger.warning(f"详情页抓取失败, 仅保留列表字段: {item['url']}")
        yield item


def _crawl(targets: list[dict]) -> list[dict]:
    """进程内运行一次 Scrapy 并收集条目"""
    items: list[dict] = []

    def collect_item(item, **kwargs):
        # 信号回调会附带 signal/sender 等额外关键字参数, 用 **kwargs 兜住
        items.append(dict(item))

    process = CrawlerProcess(settings={"LOG_ENABLED": False})
    crawler = process.create_crawler(GubaListSpider)
    crawler.signals.connect(collect_item, signal=signals.item_scraped)
    process.crawl(crawler, targets=targets)
    process.start()
    return items


def collect(targets: list[dict]) -> list[dict]:
    """采集给定目标并返回条目.

    Scrapy 的事件循环(reactor)每个进程只能启动一次, 所以放到独立子进程里执行,
    这样在 LangGraph 的重试循环中可以反复调用。
    """
    proc = subprocess.run(
        [sys.executable, "-m", "server.core.claw", "collect"],
        input=json.dumps(targets, ensure_ascii=False),
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        logger.error(f"采集子进程异常: {proc.stderr.strip()[-500:]}")
        return []
    return json.loads(proc.stdout)


def _collect_cli() -> None:
    """子进程入口: 从 stdin 读目标, 采集后将条目 JSON 写到 stdout"""
    targets = json.loads(sys.stdin.read() or "[]")
    print(json.dumps(_crawl(targets), ensure_ascii=False))


def run(output: str = "./claw_items.jsonl"):
    """启动爬虫, 抓取结果以 JSON Lines 落盘"""
    process = CrawlerProcess(
        settings={
            "FEEDS": {output: {"format": "jsonlines", "encoding": "utf8", "overwrite": True}},
        }
    )
    process.crawl(GubaListSpider)
    process.start()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "collect":
        # 子进程入口(collect() 内部会以该参数拉起本模块), 必须优先分发
        _collect_cli()
    else:
        targets = load_targets()
        result = collect(targets)
        for item in result:
            print(json.dumps(item, ensure_ascii=False))
        logger.info(f"共采集 {len(result)} 条")
