import { useEffect, useState } from 'react'
import type { Json } from '../api'
import { get, post } from '../api'
import { OUTCOME_COLOR } from '../types'

type Props = { tenant: string; version: number; onNodeClick: (id: string) => void; onChanged: () => void }

const fmt = (ts: number) => (ts ? new Date(ts * 1000).toISOString().slice(0, 16).replace('T', ' ') : '')

export default function MemoryPanel({ tenant, version, onNodeClick, onChanged }: Props) {
  const [answers, setAnswers] = useState<Json[]>([])
  const [actions, setActions] = useState<Json[]>([])
  const [mail, setMail] = useState<Json[]>([])
  useEffect(() => {
    get(`/api/answers?tenant=${tenant}`).then(setAnswers).catch(() => {})
    get(`/api/actions?tenant=${tenant}`).then(setActions).catch(() => {})
    get(`/api/notifications?tenant=${tenant}`).then(setMail).catch(() => {})
  }, [tenant, version])

  const drafts = mail.filter((m) => m.status === 'DRAFT')
  return (
    <div className="panel">
      <h3>Episodic memory: past answers</h3>
      <p className="hint">Each answer is a node with CITED edges, so a later revocation finds who was told something that is no longer supported.</p>
      {answers.map((a) => (
        <div key={a.id} className={`item ${a.no_longer_supported.length ? 'red' : ''}`}>
          <span className="badge" style={{ color: OUTCOME_COLOR[a.outcome] }}>
            {a.outcome}
          </span>{' '}
          <b>{a.asked_by ?? 'anonymous'}</b>: “{a.question}”
          <div className="path">
            {fmt(a.ts)} · cited {a.cited.map((c: string) => (
              <button key={c} className="idlink" onClick={() => onNodeClick(c)}>
                {c}
              </button>
            ))}
            {a.no_longer_supported.length > 0 && <b className="red"> · no longer supported: {a.no_longer_supported.join(', ')}</b>}
          </div>
        </div>
      ))}
      <h3>Action audit log</h3>
      {actions.length === 0 && <div className="hint">No actions yet.</div>}
      {actions.map((a) => (
        <div key={a.id} className="item">
          <span className={`badge ${a.status === 'APPROVED' ? 'green' : a.status === 'PENDING' ? 'amber' : ''}`}>{a.status}</span> <code>{a.id}</code>{' '}
          <b>{a.kind}</b>{' '}
          <button className="idlink" onClick={() => onNodeClick(a.target)}>
            {a.target}
          </button>
          <div className="path">
            {a.summary}
            {a.reason ? ` · reason: ${a.reason}` : ''} {a.approved_by ? ` · by ${a.approved_by} at ${fmt(a.decided_at)}` : ''}
          </div>
        </div>
      ))}
      <h3>
        Outbox ({drafts.length} draft{drafts.length === 1 ? '' : 's'})
        {drafts.length > 0 && (
          <button
            className="ok small"
            style={{ marginLeft: 8 }}
            onClick={async () => {
              await post('/api/notifications/send', { tenant, ids: drafts.map((d) => d.id) })
              onChanged()
            }}
          >
            Approve and send all
          </button>
        )}
      </h3>
      {mail.map((m) => (
        <div key={m.id} className="mail">
          <div>
            <span className={`badge ${m.status === 'SENT' ? 'green' : 'amber'}`}>{m.status}</span> <b>To:</b> {m.to}
          </div>
          <div>
            <b>{m.subject}</b>
          </div>
          <div className="body">{m.body}</div>
        </div>
      ))}
    </div>
  )
}
