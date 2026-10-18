import { useState } from 'react'
import type { Json } from '../api'
import { post } from '../api'

const PRESETS = [
  {
    label: 'Corroborate TTL',
    kind: 'SLACK',
    title: '#security: confirming token lifetime',
    author_id: 'P15',
    trust: 0.6,
    text: 'Confirming for the audit: auth-service access tokens expire after 15 minutes since the August change.',
  },
  {
    label: 'Contradict retention',
    kind: 'EMAIL',
    title: 'Re: event-bus storage costs',
    author_id: 'P02',
    trust: 0.6,
    text: 'Heads up: the event-bus stream retention is 24 hours from next week to cut storage costs.',
  },
  {
    label: 'New fact',
    kind: 'POSTMORTEM',
    title: 'Postmortem: search-service outage (Oct 2026)',
    author_id: 'P18',
    trust: 0.95,
    text: 'search-service failover to the standby cluster takes 20 minutes. The search-service on-call must page Platform when OpenSearch shards go red.',
  },
]

type Props = { tenant: string; people: Json[]; onChanged: () => void; onHighlight: (ids: string[]) => void; onNodeClick: (id: string) => void }

export default function IngestPanel({ tenant, people, onChanged, onHighlight, onNodeClick }: Props) {
  const [form, setForm] = useState({ ...PRESETS[0] })
  const [res, setRes] = useState<Json | null>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit() {
    setBusy(true)
    setErr('')
    try {
      const { label: _l, ...body } = form
      void _l
      const r = await post('/api/ingest', { tenant, ...body })
      setRes(r)
      onHighlight([r.source_id, ...r.created.map((c: Json) => c.id), ...r.corroborated, ...r.audit.contested])
      onChanged()
    } catch (e) {
      setErr(String(e))
    }
    setBusy(false)
  }

  return (
    <div className="panel">
      <h3>Ingest agent</h3>
      <p className="hint">
        Writes a Source, extracts claims as PROPOSED with DERIVED_FROM edges, and merges with existing claims that state the same
        (key, value). Then the <b>auditor</b> runs: two independent roots → CONFIRMED, same key with a different value → CONTRADICTS +
        CONTESTED.
      </p>
      <div className="row wrap">
        {PRESETS.map((p) => (
          <button key={p.label} className="chip" onClick={() => setForm({ ...p })}>
            {p.label}
          </button>
        ))}
      </div>
      <div className="row">
        <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
          {['SLACK', 'EMAIL', 'ADR', 'POSTMORTEM', 'MEMO'].map((k) => (
            <option key={k}>{k}</option>
          ))}
        </select>
        <select value={form.author_id} onChange={(e) => setForm({ ...form, author_id: e.target.value })}>
          {people.map((p: Json) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <input type="number" min={0} max={1} step={0.05} value={form.trust} onChange={(e) => setForm({ ...form, trust: Number(e.target.value) })} title="trust" style={{ width: 70 }} />
      </div>
      <input className="reason" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Title" />
      <textarea rows={4} value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} />
      <button onClick={submit} disabled={busy}>
        {busy ? 'Ingesting…' : 'Ingest source'}
      </button>
      {err && <div className="error">{err}</div>}
      {res && (
        <div className="cascade">
          <div className="hint">
            <button className="idlink" onClick={() => onNodeClick(res.source_id)}>
              {res.source_id}
            </button>{' '}
            · extraction: {res.method}
          </div>
          {res.created.map((c: Json) => (
            <div key={c.id} className="item">
              <span className="badge blue">new</span>{' '}
              <button className="idlink" onClick={() => onNodeClick(c.id)}>
                {c.id}
              </button>{' '}
              {c.text} {c.key && <code>{c.key}={c.value}</code>}
            </div>
          ))}
          {res.corroborated.map((id: string) => (
            <div key={id} className="item green">
              <span className="badge green">corroborated</span>{' '}
              <button className="idlink" onClick={() => onNodeClick(id)}>
                {id}
              </button>{' '}
              gained a second independent root
            </div>
          ))}
          <div className="hint">
            Auditor: confirmed [{res.audit.confirmed.join(', ')}] · contested [{res.audit.contested.join(', ')}] · resolved [
            {res.audit.resolved.join(', ')}]
          </div>
        </div>
      )}
    </div>
  )
}
