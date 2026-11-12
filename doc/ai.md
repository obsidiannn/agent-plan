看下这个项目 分为 服务端 server/ 跟客户端 frontend/
其中 server/ 的 rest api /api/agent/chroma 是rag 知识库的问答agent, 我现在需要你进行改造, 
在页面 /agent/rag 路径下, 我希望你增加一个侧边栏, 侧边栏展示的是 chroma 所有已经录入的文档, 同时在侧边栏有一个上传按钮,

    上传按钮:
        可以进行txt文件上传(入参是文件名称+文件选择), txt文件上传会往chroma 写入, 这个时候实际上会调用 core/chroma_rag.py 的拆词导入 chroma
    
    侧边栏 对文件列表的某个文件选中:
        就会切换这个文档的上下文, 这个时候问答都会围绕这篇文档来进行, 这需要你对交互以及 chroma_rag.py进行改造
    对chroma_rag.py的改造:
        1.需要集成mcp协议, 你看下 server/mcp 目录, 是否需要增加一个 chroma_rag的目录
        2.rag agent 需要封装几个tools ,你看是否可会把 查询 chroma 做成一个tools
    
你按照上文要求来进行改造,有不懂的问我
