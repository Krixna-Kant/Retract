import { useEffect, useState } from 'react'
import type { Json } from '../api'
import { post } from '../api'

type Props = {
  tenant: string
  targets: Json
  preset?: { id: string; nonce: number }
  onCascade: (cas: Json | null) => void
  onChanged: () => void
  onNodeClick: (id: string) => void
}

const REASONS: Record<string, string> = {
  'SRC-MEMO-7': 'Ledgerly retracted the memo: the figures describe the Enterprise tier, Northwind is on the Growth tier.',
  'SRC-EMAIL-13': 'Phishing: sent from the lookalike domain northwind-billing.co, not from Ledgerly.',
  'DEC-12': 'Finance reversed the Ledgerly decision after the pricing review.',
}

export default function RetractPanel({ tenant, targets, preset, onCascade, onChanged, onNodeClick }: Props) {
  const [target, setTarget] = useState('SRC-MEMO-7')
  const [action, setAction] = useState('revoke')
  const [reason, setReason] = useState(REASONS['SRC-MEMO-7'])
  const [cas, setCas] = useState<Json | null>(null)
  const [pending, setPending] = useState<Json | null>(null)
  const [applied, setApplied] = useState<Json | null>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const kindOf = (id: string) => (id.startsWith('DEC-') ? 'Decision' : id.startsWith('C-') ? 'Claim' : 'Source')
  const src = targets?.sources?.find((s: Json) => s.id === target)
  const dec = targets?.decisions?.find((d: Json) => d.id === target)
  const isDead = src ? src.revoked || src.quarantined : dec ? dec.status !== 'ACTIVE' : false

  function choose(id: string) {
    setTarget(id)
    setAction(kindOf(id) === 'Decision' ? 'reverse' : id === 'SRC-EMAIL-13' ? 'quarantine' : 'revoke')
    setReason(REASONS[id] ?? '')
    setCas(null)
    setPending(null)
    setApplied(null)
    setErr('')
  }

  useEffect(() => {
    if (preset) choose(preset.id)
  }, [preset?.nonce]) // eslint-disable-line react-hooks/exhaustive-deps

  async function run<T>(fn: () => Promise<T>) {
    setBusy(true)
    setErr('')
    try {
      return await fn()
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
    }
  }

  const preview = () =>
    run(async () => {
      const r = await post('/api/preview', { tenant, target_id: target, action })
      setCas(r.result)
      setPending(null)
      setApplied(null)
      onCascade(r.result)
    })

  const request = (kind = action) =>
    run(async () => {
      const r = await post('/api/actions', { tenant, kind, target_id: target, reason })
      setPending(r.result)
      onChanged()
    })

  const decide = (ok: boolean) =>
    run(async () => {
      const r = await post(`/api/actions/${pending.action_id}/${ok ? 'approve' : 'reject'}`, { tenant, approver: 'human:ui' })
      setPending(null)
      if (ok) {
        setApplied(r)
        if (r.invalidated) onCascade(r)
      } else {
        setCas(null)
        onCascade(null)
      }
      onChanged()
    })

  const n = (x: Json[] | undefined) => x?.length ?? 0

  return (
    <div className="panel">
      <h3>Retract a source or decision</h3>
      <p className="hint">
        Preview is a dry run: graph traversal finds every claim that loses <b>all</b> grounded support. Nothing changes until a
        human approves.
      </p>
      <div className="row">
        <select value={target} onChange={(e) => choose(e.target.value)}>
          {kindOf(target) === 'Claim' && (
            <optgroup label="Claim">
              <option value={target}>{target} (retract this claim)</option>
            </optgroup>
          )}
          <optgroup label="Sources (planted scenarios first)">
            {targets?.sources?.map((s: Json) => (
              <option key={s.id} value={s.id}>
                {s.revoked ? '✕ ' : s.quarantined ? '⛔ ' : ''}
                {s.id} · {s.title.slice(0, 44)} ({s.dependents})
              </option>
            ))}
          </optgroup>
          <optgroup label="Decisions">
            {targets?.decisions?.map((d: Json) => (
              <option key={d.id} value={d.id}>
                {d.status !== 'ACTIVE' ? `[${d.status}] ` : ''}
                {d.id} · {d.title.slice(0, 48)}
              </option>
            ))}
          </optgroup>
        </select>
      </div>
      <div className="row">
        <div className="seg">
          {(kindOf(target) === 'Source' ? ['revoke', 'quarantine'] : kindOf(target) === 'Decision' ? ['reverse'] : ['retract']).map((a) => (
            <button key={a} className={action === a ? 'on' : ''} onClick={() => setAction(a)}>
              {a}
            </button>
          ))}
        </div>
        <button className="ghost" onClick={() => onNodeClick(target)}>
          Inspect
        </button>
      </div>
      <input className="reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (stored on the node and the action)" />
      <div className="row">
        <button onClick={preview} disabled={busy || isDead}>
          Preview cascade
        </button>
        {cas && !pending && !applied && (
          <button className="warn" onClick={() => request()} disabled={busy}>
            Request {action}
          </button>
        )}
        {isDead && (
          <button className="ghost" onClick={() => request('rollback')} disabled={busy}>
            Request rollback
          </button>
        )}
      </div>
      {err && <div className="error">{err}</div>}

      {pending && (
        <div className="pending">
          <div className="pending-head">
            <span className="badge amber">PENDING APPROVAL</span> <code>{pending.action_id}</code>
          </div>
          <div>
            <b>{pending.kind}</b> {pending.target}: {pending.summary}
          </div>
          <div className="hint">Nothing has changed in the graph yet.</div>
          <div className="row">
            <button className="ok" onClick={() => decide(true)} disabled={busy}>
              Approve
            </button>
            <button className="ghost" onClick={() => decide(false)} disabled={busy}>
              Reject
            </button>
          </div>
        </div>
      )}

      {cas && (
        <div className="cascade">
          <div className="stats">
            <div className="stat red">
              <b>{n(cas.invalidated)}</b>
              <span>lose all support</span>
            </div>
            <div className="stat green">
              <b>{n(cas.survived)}</b>
              <span>survive independently</span>
            </div>
            <div className="stat violet">
              <b>{n(cas.decisions_at_risk)}</b>
              <span>decisions unsupported</span>
            </div>
            <div className="stat pink">
              <b>{n(cas.owners)}</b>
              <span>owners to tell</span>
            </div>
          </div>
          {n(cas.invalidated) > 0 && (
            <>
              <h4>Lose all support → {cas.new_status}</h4>
              {cas.invalidated.map((c: Json) => (
                <div key={c.id} className="item red">
                  <button className="idlink" onClick={() => onNodeClick(c.id)}>
                    {c.id}
                  </button>{' '}
                  {c.text}
                  <div className="path">via {c.via.join(' → ')} ({c.hops} hop{c.hops > 1 ? 's' : ''})</div>
                </div>
              ))}
            </>
          )}
          {n(cas.survived) > 0 && (
            <>
              <h4>Survive on independent support</h4>
              {cas.survived.map((c: Json) => (
                <div key={c.id} className="item green">
                  <button className="idlink" onClick={() => onNodeClick(c.id)}>
                    {c.id}
                  </button>{' '}
                  {c.text}
                  <div className="path">saved by {c.support_path.join(' → ')}</div>
                </div>
              ))}
            </>
          )}
          {n(cas.decisions_at_risk) + n(cas.decisions_weakened) > 0 && (
            <>
              <h4>Decisions</h4>
              {cas.decisions_at_risk.map((d: Json) => (
                <div key={d.id} className="item violet">
                  <b>{d.id}</b> {d.title} — <b>no remaining support</b> (owner {d.owners.join(', ')})
                </div>
              ))}
              {cas.decisions_weakened.map((d: Json) => (
                <div key={d.id} className="item">
                  <b>{d.id}</b> {d.title} — weakened, {d.remaining_support} supporting claim(s) left
                </div>
              ))}
            </>
          )}
          {n(cas.owners) > 0 && (
            <>
              <h4>Who must be told</h4>
              {cas.owners.map((o: Json) => (
                <div key={o.id} className="item pink">
                  <b>{o.name}</b> ({o.team}) owns {[...(o.owns ?? []), ...(o.decisions ?? [])].join(', ')} · {o.claims.length} claim(s)
                </div>
              ))}
            </>
          )}
          {n(cas.stale_answers) > 0 && (
            <>
              <h4>Past answers that are now unsupported</h4>
              {cas.stale_answers.map((a: Json) => (
                <div key={a.id} className="item">
                  <b>{a.asked_by}</b> was told: “{a.question}” (cited {a.cited.join(', ')})
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {applied && (
        <div className="applied">
          <span className="badge green">APPLIED</span> {applied.action_id}
          {applied.drift && <span className="badge amber">graph changed since preview, recomputed</span>}
          {applied.audit && (
            <div className="hint">
              Auditor: {applied.audit.confirmed.length} confirmed, {applied.audit.demoted.length} demoted (lost corroboration),{' '}
              {applied.audit.resolved.length} contest(s) resolved
              {applied.restored ? `, ${applied.restored.length} restored` : ''}
            </div>
          )}
          {applied.restored && <div className="hint">Restored claims: {applied.restored.join(', ') || 'none'}</div>}
          {applied.notifications?.length > 0 && (
            <>
              <h4>Drafted notifications ({applied.notifications.length})</h4>
              {applied.notifications.map((m: Json) => (
                <div key={m.id} className="mail">
                  <div>
                    <b>To:</b> {m.name} {m.email ? `<${m.email}>` : ''}
                  </div>
                  <div>
                    <b>{m.subject}</b>
                  </div>
                  <div className="body">{m.body}</div>
                </div>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  )
}
