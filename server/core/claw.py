# coding: utf-8
"""东方财富股吧列表爬虫

数据来源: claw_task(任务表) + clas_task_detail(任务明细表)
最终抓取地址 = base_url % claw_param
"""
import json
import subprocess
import sys
from pathlib import Path

import scrapy
from scrapy import signals
from scrapy.crawler import CrawlerProcess

from server.core.logs import logger
from server.db.server_engine import SessionLocal
from server.db.server_models import ClasTaskDetail, ClawTask

PROJECT_ROOT = Path(__file__).resolve().parents[2]
base_url = "https://guba.eastmoney.com/list,%s.html"
detail_url = "https://guba.eastmoney.com/news,002777,1792015179.html"


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


class GubaListSpider(scrapy.Spider):
    """按库中任务配置抓取股吧列表页"""

    name = "guba_list"
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "DOWNLOAD_DELAY": 3,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS": 1,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "DEFAULT_REQUEST_HEADERS": {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Referer": "https://guba.eastmoney.com/",
        },
    }

    def __init__(self, targets: list[dict] | None = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 未显式传入目标时, 回退到从库里读取
        self.targets = targets if targets is not None else load_targets()

    async def start(self):
        for target in self.targets:
            yield scrapy.Request(
                target["url"],
                callback=self.parse_list,
                meta={"target": target},
                dont_filter=True,
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
            yield scrapy.Request(
                item["url"],
                callback=self.parse_detail,
                errback=self.detail_failed,
                meta={"item": item},
                dont_filter=True,
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
