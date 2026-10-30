## langGraph 
> https://docs.langchain.com/oss/python/langgraph/overview?_gl=1*1pwl79s*_gcl_au*NTQ3MjUyNDE3LjE3OTMwNjk1ODY.*_ga*MTIzMDY0NTY5MS4xNzkzMDY5NTc0*_ga_47WX3HKKY2*czE3OTMzNDQ4NjYkbzYkZzAkdDE3OTMzNDQ4NjYkajYwJGwwJGgw

### 要素

* State	贯穿整个图的共享数据结构，节点读取当前状态、返回增量更新，由 LangGraph 负责合并与持久化
* Node	一个具有单一职责的工作单元，可以是 LLM 调用，也可以是普通 Python 函数（校验、路由、写文件等）
* Edge	决定当前节点结束后“下一步跑什么”。静态边按固定顺序流转；条件边根据状态动态选择路径，从而支持分支和循环


### 数据采集方案
> 通过langgraph 制定一套论坛的数据采集方案, 不同的主题(主题之间有分类可以互相关联), 主题下发表的评论/文章具备用户的主观情绪, 需要分析并落到向量库, 采集过程中需要解决 数据采集,清洗, 分类, 防爬等问题

* 根据目标论坛/主题/分类体系生成采集计划
* 待采集URL队列
* 调用反爬采集器，获取原始HTML/API响应
* 数据清洗: boilerplate去除、去重、发言边界还原
* 主题层级/关联关系维护
* 细粒度多维情绪向量提取
* 语义向量化
* 写入向量库 + 元数据落库
 * 条件边：通过→ END；不通过→ 回到 重试