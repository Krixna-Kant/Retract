import { useEffect, useState } from 'react'
import type { Json } from '../api'
import { get } from '../api'

export default function EvalPanel() {
  const [d, setD] = useState<Json | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    get('/api/eval').then(setD).catch((e) => setErr(String(e)))
  }, [])
  if (err) return <div className="panel error">{err}</div>
  if (!d) return <div className="panel">Loading…</div>
  const names = Object.keys(d.summary)
  return (
    <div className="panel">
      <h3>Mini evaluation</h3>
      <p className="hint">
        15 scripted revocation scenarios plus the full Northwind memo case. Metric: precision and recall of the predicted
        invalidated set. Synthetic and small: a sanity check, not a benchmark. Gold labels follow the same grounded-support
        definition the engine implements, so RETRACT scoring perfectly is expected; the point is where simpler methods diverge.
      </p>
      <table>
        <thead>
          <tr>
            <th>Method</th>
            <th>P</th>
            <th>R</th>
            <th>F1</th>
            <th>Exact</th>
          </tr>
        </thead>
        <tbody>
          {names.map((n) => (
            <tr key={n} className={n === 'retract' ? 'hl' : ''}>
              <td>
                <code>{n}</code>
              </td>
              <td>{d.summary[n].precision.toFixed(2)}</td>
              <td>{d.summary[n].recall.toFixed(2)}</td>
              <td>{d.summary[n].f1.toFixed(2)}</td>
              <td>
                {d.summary[n].exact}/{d.summary[n].cases}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <h4>Per scenario</h4>
      <table className="small">
        <thead>
          <tr>
            <th>Scenario</th>
            {names.map((n) => (
              <th key={n}>{n.replace('_', ' ')}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {d.cases.map((c: Json) => (
            <tr key={c.scenario}>
              <td>{c.scenario}</td>
              {names.map((n) => (
                <td key={n} className={c[n].exact ? 'okc' : 'badc'}>
                  {c[n].exact ? '✓' : `+${c[n].fp}/-${c[n].fn}`}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="hint">LLM baseline: {d.llm_provider ?? 'not run (no API key configured); run python -m eval.run_eval with a key to add it'}.</p>
    </div>
  )
}
