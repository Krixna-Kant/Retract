import { useEffect, useState } from 'react'
import type { Json } from '../api'
import { get } from '../api'

type Props = { tenant: string; version: number; onNodeClick: (id: string) => void; onPreview: (id: string) => void }

export default function InsightsPanel({ tenant, version, onNodeClick, onPreview }: Props) {
  const [d, setD] = useState<Json | null>(null)
  useEffect(() => {
    get(`/api/insights?tenant=${tenant}`).then(setD).catch(() => setD(null))
  }, [tenant, version])
  if (!d) return <div className="panel">Computing graph insights…</div>
  const max = Math.max(1, ...d.blast_radius.map((s: Json) => s.would_invalidate))
  return (
    <div className="panel">
      <h3>Single points of failure</h3>
      <p className="hint">For every live source, the cascade dry run: how many claims would lose all support if it were revoked.</p>
      {d.blast_radius.map((s: Json) => (
        <div key={s.id} className="bar-row">
          <button className="idlink" onClick={() => onNodeClick(s.id)}>
            {s.id}
          </button>
          <div className="bar">
            <div style={{ width: `${(100 * s.would_invalidate) / max}%` }} />
          </div>
          <span className="num">{s.would_invalidate}</span>
          <button className="ghost small" onClick={() => onPreview(s.id)}>
            preview
          </button>
        </div>
      ))}
      <h3>Foundational knowledge (PageRank)</h3>
      <p className="hint">
        <code>CALL algo.pageRank(NULL, 'DERIVED_FROM')</code>: roots that the most belief flows into.
      </p>
      {d.foundational.map((s: Json) => (
        <div key={s.id} className="bar-row">
          <button className="idlink" onClick={() => onNodeClick(s.id)}>
            {s.id}
          </button>
          <span className="grow">{s.title.slice(0, 40)}</span>
          <span className="num">{s.score.toFixed(3)}</span>
        </div>
      ))}
      <h3>Bus factor per system</h3>
      <p className="hint">Distinct people whose live sources ground live claims about each system.</p>
      {d.bus_factor.map((s: Json) => (
        <div key={s.id} className="bar-row">
          <span className="sys">{s.system}</span>
          <span className={`num ${s.bus_factor <= 2 ? 'red' : ''}`}>{s.bus_factor}</span>
          <span className="grow small">{s.knowers.join(', ')}</span>
        </div>
      ))}
    </div>
  )
}
