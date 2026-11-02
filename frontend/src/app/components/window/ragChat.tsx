'use client'
import { Button, Input } from "@chakra-ui/react"
import { useCallback, useEffect, useId, useRef, useState } from "react"

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

/** 生成会话 ID (不用 crypto.randomUUID: http 部署下非安全上下文, 该 API 不存在) */
const newConversationId = () => `conv_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`

/**
 * 解析单个 SSE 块
 * 后端 /api/agent/chroma 推 3 种事件: conversation(会话 ID) / on_chat_model_stream(增量文本) / error
 */
const handleSseBlock = (
  block: string,
  onChunk: (text: string) => void,
  onConversationId: (id: string) => void,
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
  }
  if (data.conversation_id) {
    // 后端若返回了自己的会话 ID, 以它为准
    onConversationId(data.conversation_id)
  }
  if (event === 'on_chat_model_stream') {
    if (data.content) {
      onChunk(data.content)
    }
  } else if (event === 'error') {
    onChunk(`\n[错误] ${data.message ?? '未知错误'}\n`)
  }
}

/**
 * 通用 RAG 聊天面板: 对接 /api/agent/chroma(Chroma 检索 + LLM 流式作答)
 * 无业务上下文依赖, 多轮对话靠 conversation_id 复用后端会话历史
 */
const RagChatPanel = () => {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streaming, setStreaming] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  // 整个组件生命周期内复用同一个会话 ID, 多轮对话共享上下文
  const conversationRef = useRef<string>(newConversationId())
  const requestId = useId()

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [messages])

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
    setStreaming(true)

    try {
      const res = await fetch('/api/agent/chroma', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          request_id: requestId,
          conversation_id: conversationRef.current,
          prompt: text,
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
          handleSseBlock(block, appendToLast, (id) => {
            conversationRef.current = id
          })
        }
      }
    } catch (e) {
      appendToLast(`\n[请求失败] ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setStreaming(false)
    }
  }, [streaming, requestId, appendToLast])

  return <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', padding: 20, gap: 12 }}>
    <div style={{ fontSize: 16, fontWeight: 600 }}>RAG Chat</div>
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
            {pending && !m.content ? <span style={{ color: '#94a3b8' }}>思考中...</span> : m.content}
          </div>
        })
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
}

export default RagChatPanel
