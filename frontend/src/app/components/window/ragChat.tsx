'use client'
import { Button, Input } from "@chakra-ui/react"
import { useCallback, useEffect, useId, useRef, useState } from "react"

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

/** 侧边栏文档项, 来自 /api/agent/chroma/documents */
interface RagDocument {
  source: string
  chunks: number
  chars: number
  uploaded_at: string
}

/** 本轮命中的文档片段(chroma 对话的 sources 事件) */
interface RagSource {
  source: string
  // 旧版灌库的切片没有段落序号, 此时为 null
  chunk_index: number | null
  snippet: string
}

/** 生成会话 ID (不用 crypto.randomUUID: http 部署下非安全上下文, 该 API 不存在) */
const newConversationId = () => `conv_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`

/** ISO 时间转成 "YYYY-MM-DD HH:mm:ss", 缺失时返回占位 */
const formatTime = (value: string) => value ? value.replace('T', ' ').slice(0, 19) : '—'

/**
 * 解析单个 SSE 块
 * 后端 /api/agent/chroma 推 4 种事件:
 * conversation(会话 ID) / sources(命中片段) / on_chat_model_stream(增量文本) / error
 */
const handleSseBlock = (
  block: string,
  handlers: {
    onChunk: (text: string) => void
    onSources: (sources: RagSource[]) => void
    onConversationId: (id: string) => void
  },
) => {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith(':')) {
      continue // sse_starlette 的心跳注释行
    }
    if (line.startsWith('event:')) {
      event = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
    }
  }
  if (dataLines.length === 0) {
    return
  }
  const data = JSON.parse(dataLines.join('\n')) as {
    content?: string
    message?: string
    conversation_id?: string
    sources?: RagSource[]
  }
  if (data.conversation_id) {
    // 后端若返回了自己的会话 ID, 以它为准
    handlers.onConversationId(data.conversation_id)
  }
  if (event === 'on_chat_model_stream') {
    if (data.content) {
      handlers.onChunk(data.content)
    }
  } else if (event === 'sources') {
    handlers.onSources(data.sources ?? [])
  } else if (event === 'error') {
    handlers.onChunk(`\n[错误] ${data.message ?? '未知错误'}\n`)
  }
}

/**
 * RAG 知识库问答面板: 对接 /api/agent/chroma(Chroma 检索 + LLM 流式作答)
 * - 左侧侧边栏: 已录入文档清单 + txt 上传(上传后拆词写入 Chroma)
 * - 选中某篇文档: 检索范围限定在该文档, 并开新会话, 对话不串上下文
 * - 选中"全部文档": 在整个知识库范围内检索
 */
const RagChatPanel = () => {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streaming, setStreaming] = useState(false)
  const [documents, setDocuments] = useState<RagDocument[]>([])
  // '' 表示全库检索; 其它值为选中的文档名
  const [selectedDoc, setSelectedDoc] = useState('')
  const [sources, setSources] = useState<RagSource[]>([])
  // 上传表单: 文件名称 + 选择的 txt 文件
  const [uploadName, setUploadName] = useState('')
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadNotice, setUploadNotice] = useState<{ ok: boolean, text: string } | null>(null)
  // 上传成功后自增, 触发文档清单重新拉取
  const [refreshKey, setRefreshKey] = useState(0)
  const listRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  // 同一篇文档内多轮复用同一个会话 ID; 切文档时换新的
  const conversationRef = useRef<string>(newConversationId())
  const requestId = useId()

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [messages])

  // 文档清单: 侧边栏初次加载 + 每次上传完成后刷新
  useEffect(() => {
    let cancelled = false
    fetch('/api/agent/chroma/documents')
      .then(res => (res.ok ? res.json() : { documents: [] }))
      .then((data: { documents?: RagDocument[] }) => {
        if (!cancelled) {
          setDocuments(Array.isArray(data.documents) ? data.documents : [])
        }
      })
      .catch(() => { /* 后端未就绪时忽略 */ })
    return () => {
      cancelled = true
    }
  }, [refreshKey])

  const resetConversation = useCallback(() => {
    conversationRef.current = newConversationId()
    setMessages([])
    setSources([])
  }, [])

  const switchDocument = useCallback((source: string) => {
    if (source === selectedDoc) {
      return
    }
    setSelectedDoc(source)
    resetConversation()
  }, [selectedDoc, resetConversation])

  const appendToLast = useCallback((chunk: string) => {
    setMessages(prev => {
      const next = [...prev]
      const last = next[next.length - 1]
      if (last?.role === 'assistant') {
        next[next.length - 1] = { ...last, content: last.content + chunk }
      }
      return next
    })
  }, [])

  const upload = useCallback(async () => {
    if (!uploadFile || uploading) {
      return
    }
    const name = (uploadName.trim() || uploadFile.name).trim()
    if (!name.toLowerCase().endsWith('.txt')) {
      setUploadNotice({ ok: false, text: '仅支持 txt 文件' })
      return
    }

    const form = new FormData()
    form.append('filename', name)
    form.append('file', uploadFile)

    setUploading(true)
    setUploadNotice(null)
    try {
      const res = await fetch('/api/agent/chroma/upload', {
        method: 'POST',
        body: form,
      })
      const data = await res.json().catch(() => null) as {
        detail?: string
        document?: RagDocument
      } | null
      if (!res.ok) {
        throw new Error(data?.detail || `HTTP ${res.status}`)
      }
      const chunks = data?.document?.chunks ?? 0
      setUploadNotice({ ok: true, text: `已导入《${name}》· ${chunks} 个片段` })
      setUploadFile(null)
      setUploadName('')
      if (fileRef.current) {
        fileRef.current.value = ''
      }
      // 刷新侧边栏清单, 并把新文档设为当前上下文
      setRefreshKey(k => k + 1)
      setSelectedDoc(name)
      resetConversation()
    } catch (e) {
      setUploadNotice({
        ok: false,
        text: `导入失败: ${e instanceof Error ? e.message : String(e)}`,
      })
    } finally {
      setUploading(false)
    }
  }, [uploadFile, uploading, uploadName, resetConversation])

  const send = useCallback(async (text: string) => {
    if (!text || streaming) {
      return
    }
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: text }, { role: 'assistant', content: '' }])
    setSources([])
    setStreaming(true)

    try {
      const res = await fetch('/api/agent/chroma', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          request_id: requestId,
          conversation_id: conversationRef.current,
          prompt: text,
          // 空串会被当成"筛选文档名为空", 必须传 null 表示全库
          document: selectedDoc || null,
        }),
      })
      if (!res.ok || !res.body) {
        const detail = await res.text().catch(() => '')
        throw new Error(`HTTP ${res.status} ${detail}`)
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          break
        }
        buffer += decoder.decode(value, { stream: true })
        // sse_starlette 默认以 \r\n 分行, 这里两种都兼容
        const blocks = buffer.split(/\r?\n\r?\n/)
        buffer = blocks.pop() ?? ''
        for (const block of blocks) {
          handleSseBlock(block, {
            onChunk: appendToLast,
            onSources: setSources,
            onConversationId: id => { conversationRef.current = id },
          })
        }
      }
    } catch (e) {
      appendToLast(`\n[请求失败] ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setStreaming(false)
    }
  }, [streaming, requestId, selectedDoc, appendToLast])

  const totalChunks = documents.reduce((sum, doc) => sum + doc.chunks, 0)

  const docRowStyle = (active: boolean) => ({
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'flex-start',
    gap: 2,
    width: '100%',
    textAlign: 'left' as const,
    padding: '8px 10px',
    border: '1px solid ' + (active ? '#3b82f6' : '#e2e8f0'),
    background: active ? '#eff6ff' : '#ffffff',
    borderRadius: 8,
    cursor: 'pointer',
    color: '#111111',
  })

  return <div style={{ display: 'flex', height: '100vh' }}>
    {/* 侧边栏: 文档清单 + 上传 */}
    <div style={{
      width: 300,
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      gap: 12,
      borderRight: '1px solid #e2e8f0',
      padding: 16,
      minHeight: 0,
    }}>
      <div style={{ fontSize: 16, fontWeight: 600 }}>知识库文档</div>

      <div style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        border: '1px solid #e2e8f0',
        borderRadius: 8,
        padding: 10,
        background: '#f8fafc',
      }}>
        <Input size="sm" placeholder="文件名称, 如 三体.txt" value={uploadName}
          disabled={uploading}
          onChange={e => setUploadName(e.target.value)} />
        <input
          ref={fileRef}
          type="file"
          accept=".txt,text/plain"
          style={{ display: 'none' }}
          onChange={e => {
            const file = e.target.files?.[0] ?? null
            setUploadFile(file)
            if (file && !uploadName.trim()) {
              setUploadName(file.name)
            }
          }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Button size="sm" variant="outline" disabled={uploading}
            onClick={() => fileRef.current?.click()}>
            选择文件
          </Button>
          <span style={{
            flex: 1,
            minWidth: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            fontSize: 12,
            color: '#64748b',
          }}>
            {uploadFile?.name ?? '未选择 txt 文件'}
          </span>
        </div>
        <Button size="sm" onClick={upload} disabled={uploading || !uploadFile}>
          {uploading ? '拆词导入中...' : '上传并入库'}
        </Button>
        {
          uploadNotice && <div style={{
            fontSize: 12,
            color: uploadNotice.ok ? '#16a34a' : '#dc2626',
          }}>{uploadNotice.text}</div>
        }
      </div>

      <div style={{ fontSize: 13, color: '#94a3b8' }}>
        共 {documents.length} 篇文档 · {totalChunks} 个片段
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={docRowStyle(selectedDoc === '')} onClick={() => switchDocument('')}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>全部文档</span>
          <span style={{ fontSize: 11, color: '#94a3b8' }}>在整库范围内检索</span>
        </div>
        {
          documents.map(doc => <div key={doc.source}
            style={docRowStyle(selectedDoc === doc.source)}
            onClick={() => switchDocument(doc.source)}>
            <span style={{
              fontSize: 13,
              fontWeight: 600,
              maxWidth: '100%',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>{doc.source}</span>
            <span style={{ fontSize: 11, color: '#94a3b8' }}>
              {doc.chunks} 片段 · {doc.chars} 字 · {formatTime(doc.uploaded_at)}
            </span>
          </div>)
        }
        {
          documents.length === 0 && <div style={{ fontSize: 12, color: '#cbd5e1' }}>
            还没有文档, 先上传一个 txt 文件
          </div>
        }
      </div>

      <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: 10, maxHeight: 220, overflowY: 'auto' }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>本轮引用</div>
        {
          sources.length === 0 ?
            <div style={{ fontSize: 12, color: '#cbd5e1' }}>提问后展示命中的文档片段</div> :
            sources.map((s, i) => <div key={`${s.source}-${s.chunk_index}-${i}`} style={{
              border: '1px solid #e2e8f0',
              borderRadius: 8,
              padding: 8,
              fontSize: 12,
              marginBottom: 8,
            }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>
                {s.source}{s.chunk_index !== null ? ` · 第 ${s.chunk_index + 1} 段` : ''}
              </div>
              <div style={{ color: '#64748b', wordBreak: 'break-word' }}>{s.snippet}</div>
            </div>)
        }
      </div>
    </div>

    {/* 对话区 */}
    <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', padding: 20, gap: 12 }}>
      <div style={{ fontSize: 16, fontWeight: 600 }}>
        RAG Chat{selectedDoc ? ` · ${selectedDoc}` : ' · 全部文档'}
      </div>
      <div ref={listRef} style={{
        flex: 1,
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        border: '1px solid #e2e8f0',
        borderRadius: 8,
        padding: 12,
      }}>
        {
          messages.map((m, i) => {
            const isUser = m.role === 'user'
            const pending = streaming && !isUser && i === messages.length - 1
            return <div key={i} style={{
              alignSelf: isUser ? 'flex-end' : 'flex-start',
              maxWidth: '85%',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              fontSize: 14,
              padding: '6px 10px',
              borderRadius: 8,
              background: isUser ? '#3b82f6' : '#f1f5f9',
              color: isUser ? '#ffffff' : '#111111',
            }}>
              {pending && !m.content ? <span style={{ color: '#94a3b8' }}>检索中...</span> : m.content}
            </div>
          })
        }
        {
          messages.length === 0 && <div style={{ fontSize: 13, color: '#94a3b8' }}>
            {selectedDoc
              ? `已选中《${selectedDoc}》, 提问将只围绕这篇文档作答`
              : '在左侧选择一篇文档, 或在全部文档范围内提问'}
          </div>
        }
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <Input placeholder="输入问题, 回车发送" value={input}
          disabled={streaming}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') {
              e.preventDefault()
              send(input.trim())
            }
          }} />
        <Button onClick={() => send(input.trim())} disabled={streaming || !input.trim()}>
          {streaming ? '生成中...' : '发送'}
        </Button>
      </div>
    </div>
  </div>
}

export default RagChatPanel
