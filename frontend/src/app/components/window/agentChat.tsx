import { Button, CloseButton, Dialog, Input } from "@chakra-ui/react"
import { useCallback, useEffect, useId, useRef, useState } from "react"


interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  // 工具调用轨迹, 与正文分开存, 避免污染 JSON 解析
  trace?: string[]
}

/** 模型按输出契约(promot.md #输出契约)返回的结构化结论 */
interface AgentContract {
  index_environment?: {
    overall?: string
    by_index?: { index_code?: string, trend?: string, recent_return?: string, verdict?: string, as_of?: string }[]
    divergence?: string | null
  }
  strategy_in_list?: string
  strategy_fit?: {
    verdict?: string
    premises_checked?: { premise?: string, holds?: boolean, evidence?: string }[]
    index_conflict?: string | null
  }
  stock_fit?: {
    conditions?: { condition?: string, result?: string, value?: string, source_tool?: string }[]
    core_failures?: string[]
    unverifiable?: string[]
  }
  entry_decision?: string
  suggest_price?: {
    value?: number | null
    basis?: string
    method?: string
    anchors?: { label?: string, value?: string, source_tool?: string, as_of?: string }[]
    as_of?: string
  }
  recommended_strategies?: {
    strategy_type?: string
    index_evidence?: string[]
    additional_data_needed?: string[]
  }[]
  conflict?: string | null
  confidence?: number
  confidence_reducers?: string[]
  data_gaps?: string[]
  assumptions?: string[]
}

/** 契约里的枚举值 -> 颜色 */
const VERDICT_COLOR: Record<string, string> = {
  buy: '#16a34a', pass: '#16a34a', effective: '#16a34a', 'risk-on': '#16a34a', true: '#16a34a',
  watch: '#d97706', unverifiable: '#d97706', degraded: '#d97706', neutral: '#d97706',
  avoid: '#dc2626', fail: '#dc2626', invalid: '#dc2626', 'risk-off': '#dc2626', false: '#dc2626',
}

/** 从模型输出里抠出 JSON: 容忍 ``` 包裹和前后废话, 解析不了返回 null 走纯文本 */
const parseContract = (raw: string): AgentContract | null => {
  const start = raw.indexOf('{')
  const end = raw.lastIndexOf('}')
  if (start < 0 || end <= start) {
    return null
  }
  try {
    return JSON.parse(raw.slice(start, end + 1)) as AgentContract
  } catch {
    return null
  }
}

const Tag = (props: { label: string, value?: string }) => props.value ? <span style={{
  display: 'inline-block',
  padding: '1px 8px',
  borderRadius: 4,
  fontSize: 12,
  background: VERDICT_COLOR[props.value] ?? '#64748b',
  color: '#ffffff',
  marginRight: 6,
}}>
  {props.label}: {props.value}
</span> : <></>

const Line = (props: { title: string, items?: (string | null | undefined)[], color?: string }) => {
  const items = (props.items ?? []).filter(Boolean) as string[]
  return items.length === 0 ? <></> : <div style={{ marginTop: 6 }}>
    <span style={{ fontWeight: 600, color: '#334155' }}>{props.title}: </span>
    <span style={{ color: props.color ?? '#475569' }}>{items.join('；')}</span>
  </div>
}

/** 生成会话 ID (不用 crypto.randomUUID: http 部署下非安全上下文, 该 API 不存在) */
const newConversationId = () => `conv_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`

/**
 * 解析单个 SSE 块
 * 后端只推 3 种事件: on_chat_model_stream(增量文本) / on_tool_start / on_tool_end, 另有 error
 */
const handleSseBlock = (
  block: string,
  onChunk: (text: string) => void,
  onTrace: (text: string) => void,
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
    node?: string
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
  } else if (event === 'on_tool_start' || event === 'on_tool_end') {
    onTrace(`${event === 'on_tool_start' ? '调用' : '返回'} ${data.node ?? ''}`)
  } else if (event === 'error') {
    onChunk(`\n[错误] ${data.message ?? '未知错误'}\n`)
  }
}

const AgentChatDialog = (props: any) => {
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streaming, setStreaming] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  // 多轮会话: { 上下文, thread_id }, 上下文(股票+日期)一变就开新会话
  const sessionRef = useRef<{ key: string, id: string } | null>(null)
  const requestId = useId()
  const record = props.record?.record
  const buyTime = props.strategyDate || record?.strategy_date || ''
  const contextKey = `${record?.stock_code ?? ''}|${buyTime}`

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [messages])

  // 换了记录/日期 -> 清掉上一个上下文的对话
  useEffect(() => {
    setMessages([])
  }, [contextKey])

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

  const appendTrace = useCallback((text: string) => {
    setMessages(prev => {
      const next = [...prev]
      const last = next[next.length - 1]
      if (last?.role === 'assistant') {
        next[next.length - 1] = { ...last, trace: [...(last.trace ?? []), text] }
      }
      return next
    })
  }, [])

  const send = useCallback(async (text: string) => {
    if (!text || streaming || !record) {
      return
    }
    const key = `${record.stock_code ?? ''}|${buyTime}`
    if (sessionRef.current?.key !== key) {
      // 新上下文: 开新会话, 后续多轮都复用这个 conversation_id
      sessionRef.current = { key, id: newConversationId() }
    }
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: text }, { role: 'assistant', content: '' }])
    setStreaming(true)

    const ticker = record.stock_code ?? ''
    // market_code 存的是 SZ/SH 大写(来自 leading_code 拆分), 接口要小写
    const market = record.market_code?.toLowerCase() === 'sz' ? 'sz' : 'sh'
    // 系统提示词(promot.md)要求每次任务都收到三元组, 这里拼进 prompt 一起发
    const prompt = 'strategy_type: ' + record.strategy_code + '\n'
      + 'ticker: ' + ticker + '\n'
      + 'market: ' + market + '\n'
      + 'buy_time: ' + buyTime + '\n'
      + 'reason: ' + record.total_reason + '\n'
      + '\n' + text

    try {
      const res = await fetch('/api/agent/chatline', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          request_id: requestId,
          conversation_id: sessionRef.current.id,
          prompt,
          // AnalyzeRequest 约定字段, 取自当前选中的策略记录
          ticker,
          market,
          buy_time: buyTime,
          strategy_type: record.strategy_code,
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
          handleSseBlock(block, appendToLast, appendTrace, (id) => {
            sessionRef.current = { key, id }
          })
        }
      }
    } catch (e) {
      appendToLast(`\n[请求失败] ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setStreaming(false)
    }
  }, [streaming, record, buyTime, requestId, appendToLast, appendTrace])

  // 打开弹窗时把默认问题填进输入框, 由用户自己决定发不发
  useEffect(() => {
    if (!open || !record || messages.length > 0) {
      return
    }
    setInput(prev => prev)
  }, [open, record, messages.length])

  return <Dialog.Root open={open} onOpenChange={(e) => setOpen(e.open)} size="lg">
    <Dialog.Trigger asChild>
      <Button variant="subtle" style={{ marginRight: 8 }}>
        Agent Chat
      </Button>
    </Dialog.Trigger>
    <Dialog.Backdrop />
    <Dialog.Positioner>
      <Dialog.Content>
        <Dialog.Header>
          <Dialog.Title>Agent Chat</Dialog.Title>
        </Dialog.Header>
        <Dialog.Body>
          <div style={{ fontSize: 13, color: '#888', marginBottom: 8 }}>
            {
              record ?
                `${record.stock_code ?? ''} ${props.strategyDate}` :
                '请先在左侧选择一条记录'
            }
          </div>
          <div ref={listRef} style={{
            height: 360,
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: 8
          }}>
            {
              messages.map((m, i) => {
                const isUser = m.role === 'user'
                const pending = streaming && !isUser && i === messages.length - 1
                const contract = isUser ? null : parseContract(m.content)
                // 契约 JSON 是流式吐出来的, 拼完整之前先别把半截 JSON 显示出来
                const waitingJson = pending && !contract && m.content.trimStart().startsWith('{')
                return <div key={i} style={{
                  alignSelf: isUser ? 'flex-end' : 'flex-start',
                  maxWidth: '85%',
                  whiteSpace: contract ? 'normal' : 'pre-wrap',
                  wordBreak: 'break-word',
                  fontSize: 14,
                  padding: '6px 10px',
                  borderRadius: 8,
                  background: isUser ? '#3b82f6' : '#f1f5f9',
                  color: isUser ? '#ffffff' : '#111111',
                }}>
                  {
                    m.trace?.length ? <div style={{
                      fontSize: 12,
                      color: '#94a3b8',
                      marginBottom: 4
                    }}>
                      {m.trace.join(' · ')}
                    </div> : <></>
                  }
                  {
                    contract ? <ContractView data={contract} /> :
                      waitingJson || (pending && !m.content) ?
                        <span style={{ color: '#94a3b8' }}>分析中...</span> :
                        m.content
                  }
                </div>
              })
            }
          </div>
        </Dialog.Body>
        <Dialog.Footer>
          <Input placeholder="输入问题, 回车发送" value={input}
            disabled={!record || streaming}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') {
                e.preventDefault()
                send(input.trim())
              }
            }} />
          <Button onClick={() => send(input.trim())} disabled={!record || streaming || !input.trim()}>
            {streaming ? '生成中...' : '发送'}
          </Button>
        </Dialog.Footer>
        <Dialog.CloseTrigger asChild>
          <CloseButton size="sm" />
        </Dialog.CloseTrigger>
      </Dialog.Content>
    </Dialog.Positioner>
  </Dialog.Root>
}

export default AgentChatDialog
