'use client'
import { Button, Input } from "@chakra-ui/react"
import { useCallback, useEffect, useId, useRef, useState } from "react"

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

/** 全库/指定参数的立场分布(来自 /api/agent/claw/overview 或 clawChat 的 stats 事件) */
interface StanceStats {
  total: number
  stance: Record<string, number>
}

/** 可选采集参数(claw_task_detail.claw_param), 来自 /api/agent/claw/params */
interface ParamOption {
  claw_param: string
  task_code: string
  task_name: string
  count: number
}

/** 本轮命中的帖子(clawChat 的 sources 事件) */
interface Source {
  title: string
  url: string
  author: string
  publish_time: string
  stance: string
  task_code: string
  claw_param: string
  snippet: string
}

/** 立场配色: 沿用 A 股惯例, 看多红 / 看空绿 / 中性灰 */
const STANCE_COLOR: Record<string, string> = {
  '积极': '#ef4444',
  '消极': '#22c55e',
  '中性': '#94a3b8',
}
const STANCE_ORDER = ['积极', '消极', '中性']

/** 生成会话 ID (不用 crypto.randomUUID: http 部署下非安全上下文, 该 API 不存在) */
const newConversationId = () => `conv_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`

/** 解析单个 SSE 块, 按事件名分发 */
const handleSseBlock = (
  block: string,
  handlers: {
    onChunk: (text: string) => void
    onStats: (stats: StanceStats) => void
    onSources: (sources: Source[]) => void
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
    total?: number
    stance?: Record<string, number>
    sources?: Source[]
  }
  if (data.conversation_id) {
    handlers.onConversationId(data.conversation_id)
  }
  if (event === 'stats') {
    handlers.onStats({ total: data.total ?? 0, stance: data.stance ?? {} })
  } else if (event === 'sources') {
    handlers.onSources(data.sources ?? [])
  } else if (event === 'on_chat_model_stream') {
    if (data.content) {
      handlers.onChunk(data.content)
    }
  } else if (event === 'error') {
    handlers.onChunk(`\n[错误] ${data.message ?? '未知错误'}\n`)
  }
}

/**
 * 股吧舆情对话面板: 对接 /api/agent/clawChat
 * - 左侧: 多轮对话(SSE 流式), 基于 claw_graph 落库的帖子作答
 * - 右侧: 按 claw_param(采集参数, 如股票代码)切换的立场分布 + 本轮命中来源
 * 切换参数即视为新会话: 对话历史与命中的帖子都会重置, 保证不同票的结果不串。
 */
const ClawChatPanel = () => {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streaming, setStreaming] = useState(false)
  const [params, setParams] = useState<ParamOption[]>([])
  const [clawParam, setClawParam] = useState('')
  const [stats, setStats] = useState<StanceStats>({ total: 0, stance: {} })
  const [sources, setSources] = useState<Source[]>([])
  const listRef = useRef<HTMLDivElement>(null)
  // 同一个参数内多轮复用同一会话 ID; 切参数时换新的, 上下文不跨票
  const conversationRef = useRef<string>(newConversationId())
  const requestId = useId()

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [messages])

  // 可选参数清单(带已入库条数), 供按票区分
  useEffect(() => {
    fetch('/api/agent/claw/params')
      .then(res => (res.ok ? res.json() : []))
      .then((data: ParamOption[]) => setParams(Array.isArray(data) ? data : []))
      .catch(() => { /* 后端未就绪时忽略 */ })
  }, [])

  // 立场分布跟随所选参数: 未选=全库, 选定=只统计该 code
  useEffect(() => {
    const query = clawParam ? `?claw_param=${encodeURIComponent(clawParam)}` : ''
    fetch(`/api/agent/claw/overview${query}`)
      .then(res => (res.ok ? res.json() : null))
      .then((data: StanceStats | null) => {
        if (data) {
          setStats({ total: data.total ?? 0, stance: data.stance ?? {} })
        }
      })
      .catch(() => { /* 忽略 */ })
  }, [clawParam])

  const switchParam = useCallback((value: string) => {
    if (value === clawParam) {
      return
    }
    conversationRef.current = newConversationId()
    setClawParam(value)
    setMessages([])
    setSources([])
    setStats({ total: 0, stance: {} })
  }, [clawParam])

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

  const send = useCallback(async (text: string) => {
    if (!text || streaming) {
      return
    }
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: text }, { role: 'assistant', content: '' }])
    setSources([])
    setStreaming(true)

    try {
      const res = await fetch('/api/agent/clawChat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          request_id: requestId,
          conversation_id: conversationRef.current,
          prompt: text,
          // 空串会被后端当成"筛选 claw_param 为空"的帖子, 必须传 null 表示全库
          claw_param: clawParam || null,
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
            onStats: setStats,
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
  }, [streaming, requestId, clawParam, appendToLast])

  const current = params.find(p => p.claw_param === clawParam)

  return <div style={{ display: 'flex', height: '100vh', padding: 20, gap: 16 }}>
    <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontSize: 16, fontWeight: 600 }}>
        股吧舆情 Chat{clawParam ? ` · ${clawParam}` : ' · 全部参数'}
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
        {messages.length === 0 && <div style={{ fontSize: 13, color: '#94a3b8' }}>
          试着问: &quot;最近大家对这个票的倾向如何?&quot; / &quot;有哪些看空的理由?&quot;
        </div>}
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

    <div style={{
      width: 320,
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      gap: 12,
      borderLeft: '1px solid #e2e8f0',
      paddingLeft: 16,
      overflowY: 'auto',
    }}>
      <div style={{ fontSize: 15, fontWeight: 600 }}>用户倾向分布</div>
      <select
        value={clawParam}
        disabled={streaming}
        onChange={e => switchParam(e.target.value)}
        style={{
          fontSize: 13,
          padding: '4px 6px',
          border: '1px solid #cbd5e1',
          borderRadius: 6,
          background: '#ffffff',
        }}>
        <option value="">全部参数</option>
        {
          params.map(p => <option key={p.claw_param} value={p.claw_param}>
            {p.claw_param}（{p.count} 条）
          </option>)
        }
      </select>
      <div style={{ fontSize: 12, color: '#94a3b8' }}>
        {current ? `${current.task_name} · ` : ''}共 {stats.total} 条帖子
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {
          STANCE_ORDER.map(label => {
            const count = stats.stance[label] ?? 0
            const pct = stats.total ? Math.round((count / stats.total) * 100) : 0
            return <div key={label}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                <span style={{ color: STANCE_COLOR[label], fontWeight: 600 }}>{label}</span>
                <span style={{ color: '#64748b' }}>{count} · {pct}%</span>
              </div>
              <div style={{ height: 6, background: '#e2e8f0', borderRadius: 3, marginTop: 4 }}>
                <div style={{
                  width: `${pct}%`,
                  height: '100%',
                  borderRadius: 3,
                  background: STANCE_COLOR[label],
                }} />
              </div>
            </div>
          })
        }
      </div>

      <div style={{ fontSize: 15, fontWeight: 600, marginTop: 8 }}>命中来源</div>
      {
        sources.length === 0 ?
          <div style={{ fontSize: 12, color: '#cbd5e1' }}>提问后展示本轮检索到的帖子</div> :
          sources.map((s, i) => {
            const color = STANCE_COLOR[s.stance] ?? '#94a3b8'
            return <div key={i} style={{
              border: '1px solid #e2e8f0',
              borderRadius: 8,
              padding: 8,
              fontSize: 13,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{
                  flexShrink: 0,
                  fontSize: 11,
                  color: '#ffffff',
                  background: color,
                  borderRadius: 4,
                  padding: '0 4px',
                }}>{s.stance || '未知'}</span>
                <span style={{ fontWeight: 600, wordBreak: 'break-word' }}>{s.title}</span>
              </div>
              <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>
                {s.claw_param} · {s.author} · {s.publish_time}
                {
                  s.url && <>
                    {' · '}
                    <a href={s.url} target="_blank" rel="noreferrer" style={{ color: '#3b82f6' }}>原文</a>
                  </>
                }
              </div>
            </div>
          })
      }
    </div>
  </div>
}

export default ClawChatPanel
