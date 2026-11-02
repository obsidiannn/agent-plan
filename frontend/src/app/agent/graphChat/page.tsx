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

/** /api/agent/graph/start 与 /resume 的统一返回结构 */
interface GraphResult {
  conversation_id?: string
  status: 'interrupted' | 'finished'
  pending: Pending | null
  messages: ChatMessage[]
}

/** 生成会话 ID (不用 crypto.randomUUID: http 部署下非安全上下文, 该 API 不存在) */
const newConversationId = () => `conv_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`

/**
 * 人工审批工作流面板: 对接 /api/agent/graph/start + /api/agent/graph/resume
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
  const listRef = useRef<HTMLDivElement>(null)
  const conversationRef = useRef<string>(newConversationId())
  const requestId = useId()

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [messages, pending])

  const call = useCallback(async (url: string, body: Record<string, unknown>) => {
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
        conversationRef.current = data.conversation_id
      }
      setMessages(data.messages ?? [])
      setPending(data.pending ?? null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }, [])

  const send = useCallback((text: string) => {
    if (!text || busy || pending) {
      return
    }
    setInput('')
    // 乐观回显用户消息, 后端返回后以服务端消息为准
    setMessages(prev => [...prev, { role: 'user', content: text }])
    call('/api/agent/graphChat', {
      request_id: requestId,
      conversation_id: conversationRef.current,
      prompt: text,
    })
  }, [busy, pending, requestId, call])

  const decide = useCallback((decision: 'approve' | 'reject') => {
    if (busy) {
      return
    }
    call('/api/agent/graph/resume', {
      request_id: requestId,
      conversation_id: conversationRef.current,
      decision,
    })
  }, [busy, requestId, call])

  const reset = useCallback(() => {
    conversationRef.current = newConversationId()
    setMessages([])
    setPending(null)
    setError('')
  }, [])

  return <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', padding: 20, gap: 12 }}>
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <div style={{ fontSize: 16, fontWeight: 600 }}>Graph 人工审批 Chat</div>
      <Button size="sm" variant="subtle" onClick={reset} disabled={busy}>新会话</Button>
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
}

export default GraphChatPanel
