'use client'
import { Button, Input } from "@chakra-ui/react"
import { useCallback, useEffect, useId, useRef, useState } from "react"

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

/** 待审批内容(来自后端 interrupt) */
interface Pending {
  question: string
  action: string
}

/** /api/agent/graphChat、/resume、/history 的统一返回结构 */
interface GraphResult {
  conversation_id?: string
  status: 'interrupted' | 'finished'
  pending: Pending | null
  messages: ChatMessage[]
}

/** /api/agent/graph/sessions 的列表项 */
interface SessionItem {
  conversation_id: string
  title: string
  updated_at: string | null
  message_count: number
  status: 'interrupted' | 'finished'
}

/** 生成会话 ID (不用 crypto.randomUUID: http 部署下非安全上下文, 该 API 不存在) */
const newConversationId = () => `conv_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`

/** 后端 ts 带 6 位微秒, Date 只认 3 位, 先截断再解析 */
const formatTime = (ts?: string | null) => {
  if (!ts) {
    return ''
  }
  const d = new Date(ts.replace(/(\.\d{3})\d+/, '$1'))
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString('zh-CN', { hour12: false })
}

/**
 * 人工审批工作流面板: 对接 /api/agent/graphChat + /api/agent/graph/resume
 * - 左侧列出历史会话(/api/agent/graph/sessions), 点击加载完整消息(/api/agent/graph/history)
 * - 发送请求 -> 后端在审批节点挂起, 返回 pending
 * - 点"批准/拒绝" -> 带上同一个 conversation_id 恢复执行
 * 每次响应都由后端返回完整消息列表, 前端直接覆盖渲染, 不在本地拼接
 */
const GraphChatPanel = () => {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [pending, setPending] = useState<Pending | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [sessions, setSessions] = useState<SessionItem[]>([])
  const [conversationId, setConversationId] = useState<string>(newConversationId)
  const listRef = useRef<HTMLDivElement>(null)
  const requestId = useId()

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [messages, pending])

  /** 拉取历史会话列表, 返回列表供调用方决定是否自动打开最新一条 */
  const refreshSessions = useCallback(async (): Promise<SessionItem[]> => {
    try {
      const res = await fetch('/api/agent/graph/sessions')
      if (!res.ok) {
        return []
      }
      const data = await res.json() as { sessions: SessionItem[] }
      const list = data.sessions ?? []
      setSessions(list)
      return list
    } catch {
      return []
    }
  }, [])

  /** 打开某个历史会话: 加载消息并还原挂起状态 */
  const loadSession = useCallback(async (cid: string) => {
    setBusy(true)
    setError('')
    try {
      const res = await fetch(`/api/agent/graph/history?conversation_id=${encodeURIComponent(cid)}`)
      if (!res.ok) {
        const detail = await res.text().catch(() => '')
        throw new Error(`HTTP ${res.status} ${detail}`)
      }
      const data = await res.json() as GraphResult
      setConversationId(cid)
      setMessages(data.messages ?? [])
      setPending(data.pending ?? null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }, [])

  /** 发送 / 恢复共用: 请求后以服务端返回的消息为准, 并刷新历史列表 */
  const post = useCallback(async (url: string, body: Record<string, unknown>) => {
    setBusy(true)
    setError('')
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const detail = await res.text().catch(() => '')
        throw new Error(`HTTP ${res.status} ${detail}`)
      }
      const data = await res.json() as GraphResult
      if (data.conversation_id) {
        setConversationId(data.conversation_id)
      }
      setMessages(data.messages ?? [])
      setPending(data.pending ?? null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
    await refreshSessions()
  }, [refreshSessions])

  const send = useCallback((text: string) => {
    if (!text || busy || pending) {
      return
    }
    setInput('')
    // 乐观回显用户消息, 后端返回后以服务端消息为准
    setMessages(prev => [...prev, { role: 'user', content: text }])
    post('/api/agent/graphChat', {
      request_id: requestId,
      conversation_id: conversationId,
      prompt: text,
    })
  }, [busy, pending, conversationId, requestId, post])

  const decide = useCallback((decision: 'approve' | 'reject') => {
    if (busy) {
      return
    }
    post('/api/agent/graph/resume', {
      request_id: requestId,
      conversation_id: conversationId,
      decision,
    })
  }, [busy, conversationId, requestId, post])

  const newSession = useCallback(() => {
    setConversationId(newConversationId())
    setMessages([])
    setPending(null)
    setError('')
  }, [])

  // 首次进页面: 拉列表并自动打开最近一次会话
  useEffect(() => {
    refreshSessions().then(list => {
      if (list.length > 0) {
        loadSession(list[0].conversation_id)
      }
    })
  }, [refreshSessions, loadSession])

  return <div style={{ display: 'flex', height: '100vh', padding: 20, gap: 16 }}>
    <div style={{
      width: 240,
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
      borderRight: '1px solid #e2e8f0',
      paddingRight: 12,
    }}>
      <Button size="sm" onClick={newSession} disabled={busy}>+ 新会话</Button>
      <div style={{ fontSize: 12, color: '#94a3b8' }}>历史会话</div>
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
        {
          sessions.map(s => {
            const active = s.conversation_id === conversationId
            return <div key={s.conversation_id}
              onClick={() => { if (!busy) { loadSession(s.conversation_id) } }}
              style={{
                cursor: 'pointer',
                padding: '8px 10px',
                borderRadius: 8,
                fontSize: 13,
                background: active ? '#eff6ff' : 'transparent',
                border: `1px solid ${active ? '#bfdbfe' : 'transparent'}`,
              }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{
                  flex: 1,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  fontWeight: active ? 600 : 400,
                }}>{s.title}</span>
                {s.status === 'interrupted' && <span style={{
                  flexShrink: 0,
                  fontSize: 11,
                  color: '#b45309',
                  background: '#fef3c7',
                  borderRadius: 4,
                  padding: '0 4px',
                }}>待审批</span>}
              </div>
              <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>
                {formatTime(s.updated_at)} · {s.message_count} 条
              </div>
            </div>
          })
        }
        {sessions.length === 0 && <div style={{ fontSize: 12, color: '#cbd5e1' }}>暂无历史会话</div>}
      </div>
    </div>

    <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontSize: 16, fontWeight: 600 }}>Graph 人工审批 Chat</div>
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
              {m.content}
            </div>
          })
        }
        {
          pending && <div style={{
            alignSelf: 'flex-start',
            maxWidth: '85%',
            fontSize: 14,
            padding: 12,
            borderRadius: 8,
            border: '1px solid #f59e0b',
            background: '#fffbeb',
            color: '#92400e',
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
          }}>
            <div style={{ fontWeight: 600 }}>{pending.question}</div>
            <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{pending.action}</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button size="sm" colorPalette="green" onClick={() => decide('approve')} disabled={busy}>
                批准
              </Button>
              <Button size="sm" colorPalette="red" onClick={() => decide('reject')} disabled={busy}>
                拒绝
              </Button>
            </div>
          </div>
        }
        {busy && <div style={{ color: '#94a3b8', fontSize: 13 }}>处理中...</div>}
        {error && <div style={{ color: '#dc2626', fontSize: 13 }}>{error}</div>}
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <Input placeholder="输入要执行的操作, 回车提交审批" value={input}
          disabled={busy || !!pending}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') {
              e.preventDefault()
              send(input.trim())
            }
          }} />
        <Button onClick={() => send(input.trim())} disabled={busy || !!pending || !input.trim()}>
          提交
        </Button>
      </div>
    </div>
  </div>
}

export default GraphChatPanel
