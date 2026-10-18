import type { Json } from '../api'
import { STATUS_COLOR } from '../types'

type Props = {
  data: Json | null
  onClose: () => void
  onNodeClick: (id: string) => void
  onPreview: (id: string) => void
  onHighlight: (nodes: string[], edges: string[][]) => void
}

function Status({ s }: { s?: string }) {
  if (!s) return null
  return (
    <span className="badge" style={{ color: STATUS_COLOR[s] ?? '#cbd5e1', borderColor: STATUS_COLOR[s] ?? '#475569' }}>
      {s}
    </span>
  )
}

export default function NodeDrawer({ data, onClose, onNodeClick, onPreview, onHighlight }: Props) {
  if (!data) return null
  const r = data.result
  const Id = ({ id }: { id: string }) => (
    <button className="idlink" onClick={() => onNodeClick(id)}>
      {id}
    </button>
  )
  return (
    <div className="drawer">
      <div className="drawer-head">
        <span className="kind">{data.kind}</span>
        <button className="ghost small" onClick={() => onHighlight(data.nodes, data.edges)}>
          highlight
        </button>
        <button className="ghost small" onClick={onClose}>
          ✕
        </button>
      </div>
      {data.kind === 'Claim' && r.found && (
        <>
          <div className="title">
            <b>{r.claim.id}</b> <Status s={r.claim.status} />
          </div>
          <div className="text">{r.claim.text}</div>
          <div className="hint">
            about {r.claim.systems.join(', ')} · written by {r.claim.written_by.join(', ')}
            {r.claim.invalidated_by ? ` · invalidated by ${r.claim.invalidated_by}` : ''}
          </div>
          <h4>
            Why do we believe this? {r.live_paths} live path(s), roots: {r.independent_roots.join(', ') || 'none'}
          </h4>
          {r.paths.map((p: Json, i: number) => (
            <div key={i} className={`path-row ${p.live ? 'live' : 'dead'}`}>
              {p.nodes.map((n: Json, j: number) => (
                <span key={n.id}>
                  {j > 0 && ' → '}
                  <Id id={n.id} />
                  {n.revoked ? ' (revoked)' : n.quarantined ? ' (quarantined)' : n.label === 'Claim' && j > 0 ? ` (${n.status})` : n.label === 'Decision' ? ` (${n.status})` : ''}
                </span>
              ))}
              <span className="tag">{p.live ? 'live' : 'dead'}</span>
            </div>
          ))}
          {r.contradicts.length > 0 && (
            <>
              <h4>Contradicts</h4>
              {r.contradicts.map((c: Json) => (
                <div key={c.id} className="item amber">
                  <Id id={c.id} /> <Status s={c.status} /> {c.text}
                </div>
              ))}
            </>
          )}
          {r.supports_decisions.length > 0 && (
            <>
              <h4>Supports decisions</h4>
              {r.supports_decisions.map((d: Json) => (
                <div key={d.id} className="item">
                  <Id id={d.id} /> {d.title} ({d.status})
                </div>
              ))}
            </>
          )}
          <button className="warn small" onClick={() => onPreview(r.claim.id)}>
            Preview retracting this claim
          </button>
        </>
      )}
      {data.kind === 'Source' && r.found && (
        <>
          <div className="title">
            <b>{r.source.id}</b> <span className="badge">{r.source.kind}</span>{' '}
            {r.source.revoked && <span className="badge red">REVOKED</span>}
            {r.source.quarantined && <span className="badge red">QUARANTINED</span>}
          </div>
          <div className="text">{r.source.title}</div>
          <div className="hint">
            trust {r.source.trust} · {r.source.authors.length ? `authored by ${r.source.authors.join(', ')}` : 'no internal author'}
            {r.source.sender ? ` · sender ${r.source.sender}` : ''}
          </div>
          <div className="quote">{r.source.text}</div>
          <h4>{r.dependents.length} claim(s) built on it</h4>
          {r.dependents.map((d: Json) => (
            <div key={d.id} className="item">
              <Id id={d.id} /> <Status s={d.status} /> {d.text} <span className="path">({d.hops} hop)</span>
            </div>
          ))}
          {r.conflicts.length > 0 && (
            <>
              <h4>Conflicts</h4>
              {r.conflicts.map((c: Json) => (
                <div key={c.claim + c.contradicts} className="item amber">
                  <Id id={c.claim} /> contradicts <Id id={c.contradicts} /> “{c.other_text}”
                </div>
              ))}
            </>
          )}
          <button className="warn small" onClick={() => onPreview(r.source.id)}>
            Preview revoking this source
          </button>
        </>
      )}
      {data.kind === 'Decision' && r.found && (
        <>
          <div className="title">
            <b>{r.decision.id}</b> <span className="badge">{r.decision.status}</span>
          </div>
          <div className="text">{r.decision.title}</div>
          <h4>Supersession chain</h4>
          {r.chain.map((c: Json) => (
            <div key={c.id} className={`item ${c.status === 'ACTIVE' ? 'green' : ''}`}>
              <Id id={c.id} /> {c.title} · {c.date} · {c.status} · {c.owners.join(', ')}
            </div>
          ))}
          <div className="hint">In force: {r.in_force ? `${r.in_force.id} ${r.in_force.title}` : 'nothing active'}</div>
          {r.supported_by.length > 0 && (
            <>
              <h4>
                Supported by ({r.live_support}/{r.supported_by.length} live)
              </h4>
              {r.supported_by.map((c: Json) => (
                <div key={c.id} className="item">
                  <Id id={c.id} /> <Status s={c.status} /> {c.text}
                </div>
              ))}
            </>
          )}
          {r.decision.status === 'ACTIVE' && (
            <button className="warn small" onClick={() => onPreview(r.decision.id)}>
              Preview reversing this decision
            </button>
          )}
        </>
      )}
      {!['Claim', 'Source', 'Decision'].includes(data.kind) && <pre className="quote">{JSON.stringify(r, null, 2)}</pre>}
    </div>
  )
}
