import { useEffect, useRef, useState } from 'react'
import type { Json } from '../api'
import { stream } from '../api'
import { OUTCOME_COLOR, OUTCOME_HELP } from '../types'

type Step = { tool: string; args: Json; brief: string; nodes: string[]; edges: string[][]; ms: number; router?: string }
type Msg =
  | { role: 'user'; text: string }
  | {
      role: 'agent'
      steps: Step[]
      outcome?: string
      answer?: string
      sources?: Json[]
      cited?: string[]
      error?: string
      done: boolean
      llm?: string | null
    }

const SUGGESTIONS = [
  'Why do we use Ledgerly for billing, and is it still current?',
  'When can finance close start each month?',
  'What do we use for the event bus, and is it current?',
  'What is the auth token TTL?',
  'What is the payments webhook endpoint?',
  'What is the disaster recovery RTO for search-service?',
  'Who knows about the billing-service?',
  'What happens if SRC-MEMO-7 is revoked?',
]

type Props = {
  tenant: string
  people: Json[]
  onStep: (nodes: string[], edges: string[][], reset: boolean) => void
  onAnswer: (nodes: string[], edges: string[][]) => void
  onNodeClick: (id: string) => void
  onDone: () => void
}

const ID_RE = /\b((?:SRC|DEC|C|ACT|A)-[A-Z0-9-]+)\b/g

function Linked({ text, onNodeClick }: { text: string; onNodeClick: (id: string) => void }) {
  const parts = text.split(ID_RE)
  return (
    <>
      {parts.map((p, i) =>
        i % 2 === 1 ? (
          <button key={i} className="idlink" onClick={() => onNodeClick(p)}>
            {p}
          </button>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  )
}

export default function Chat({ tenant, people, onStep, onAnswer, onNodeClick, onDone }: Props) {
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [user, setUser] = useState('P11')
  const [busy, setBusy] = useState(false)
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [msgs])
  useEffect(() => {
    setMsgs([])
  }, [tenant])

  async function ask(q: string) {
    if (!q.trim() || busy) return
    setBusy(true)
    setInput('')
    setMsgs((m) => [...m, { role: 'user', text: q }, { role: 'agent', steps: [], done: false }])
    const patch = (fn: (a: Extract<Msg, { role: 'agent' }>) => void) =>
      setMsgs((m) => {
        const copy = [...m]
        const last = { ...(copy[copy.length - 1] as Extract<Msg, { role: 'agent' }>) }
        last.steps = [...last.steps]
        fn(last)
        copy[copy.length - 1] = last
        return copy
      })
    let first = true
    try {
      await stream('/api/ask', { tenant, question: q, user }, (e) => {
        if (e.type === 'start') patch((a) => (a.llm = e.llm))
        if (e.type === 'step') {
          patch((a) => a.steps.push(e))
          onStep(e.nodes, e.edges, first)
          first = false
        }
        if (e.type === 'answer') {
          patch((a) => {
            a.outcome = e.outcome
            a.answer = e.answer
            a.sources = e.sources
            a.cited = e.cited
          })
          onAnswer(e.highlight.nodes, e.highlight.edges)
        }
        if (e.type === 'error') patch((a) => (a.error = e.message))
        if (e.type === 'done') patch((a) => (a.done = true))
      })
    } catch (err) {
      patch((a) => {
        a.error = String(err)
        a.done = true
      })
    }
    setBusy(false)
    onDone()
  }

  return (
    <div className="chat">
      <div className="chat-log">
        {msgs.length === 0 && (
          <div className="chat-empty">
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="chip" onClick={() => ask(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) =>
          m.role === 'user' ? (
            <div key={i} className="msg user">
              {m.text}
            </div>
          ) : (
            <div key={i} className="msg agent">
              <div className="steps">
                {m.steps.map((s, j) => (
                  <div key={j} className="step">
                    <span className="tool">{s.tool}</span>
                    <span className="args">({Object.values(s.args).map((v) => JSON.stringify(v)).join(', ')})</span>
                    <span className="ms">{s.ms} ms</span>
                    <div className="brief">
                      <Linked text={s.brief} onNodeClick={onNodeClick} />
                    </div>
                  </div>
                ))}
                {!m.done && !m.outcome && <div className="step thinking">traversing the graph…</div>}
              </div>
              {m.outcome && (
                <>
                  <div className="outcome" style={{ borderColor: OUTCOME_COLOR[m.outcome], color: OUTCOME_COLOR[m.outcome] }} title={OUTCOME_HELP[m.outcome]}>
                    {m.outcome}
                  </div>
                  <div className="answer">
                    <Linked text={m.answer ?? ''} onNodeClick={onNodeClick} />
                  </div>
                  {m.sources && m.sources.length > 0 && (
                    <div className="sources">
                      {m.sources.map((s: Json) => (
                        <button key={s.id} className="src" onClick={() => onNodeClick(s.id)} title={s.title}>
                          <b>{s.id}</b> {s.title?.slice(0, 48)}
                          {s.trust != null && <em>trust {s.trust}</em>}
                        </button>
                      ))}
                    </div>
                  )}
                  <div className="meta">
                    {m.steps.length} graph tool call(s) · router: {m.steps[0]?.router ?? 'offline'} · phrasing: {m.llm ?? 'template (no LLM)'}
                  </div>
                </>
              )}
              {m.error && <div className="error">{m.error}</div>}
            </div>
          ),
        )}
        <div ref={end} />
      </div>
      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault()
          ask(input)
        }}
      >
        <select value={user} onChange={(e) => setUser(e.target.value)} title="Asking as (answers are remembered per person)">
          {people.map((p: Json) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about Northwind… (ids like SRC-MEMO-7 work)" />
        <button disabled={busy}>{busy ? '…' : 'Ask'}</button>
      </form>
      {msgs.length > 0 && (
        <div className="chips-row">
          {SUGGESTIONS.slice(0, 6).map((s) => (
            <button key={s} className="chip tiny" onClick={() => ask(s)} disabled={busy}>
              {s.length > 34 ? s.slice(0, 32) + '…' : s}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
