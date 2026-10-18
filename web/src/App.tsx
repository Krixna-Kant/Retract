import { useCallback, useEffect, useState } from 'react'
import type { Json } from './api'
import { get, post } from './api'
import Chat from './components/Chat'
import EvalPanel from './components/EvalPanel'
import GraphView from './components/GraphView'
import IngestPanel from './components/IngestPanel'
import InsightsPanel from './components/InsightsPanel'
import MemoryPanel from './components/MemoryPanel'
import NodeDrawer from './components/NodeDrawer'
import RetractPanel from './components/RetractPanel'
import type { GLink, GNode, Highlight } from './types'
import { STATUS_COLOR, edgeKey, emptyHighlight } from './types'

const TABS = ['Retract', 'Ingest', 'Insights', 'Memory', 'Eval'] as const
type Tab = (typeof TABS)[number]

export default function App() {
  const [tenant, setTenant] = useState('northwind')
  const [meta, setMeta] = useState<Json | null>(null)
  const [graph, setGraph] = useState<{ nodes: GNode[]; links: GLink[] }>({ nodes: [], links: [] })
  const [targets, setTargets] = useState<Json>({ sources: [], decisions: [], people: [] })
  const [hl, setHl] = useState<Highlight>(emptyHighlight())
  const [focusKey, setFocusKey] = useState(0)
  const [tab, setTab] = useState<Tab>('Retract')
  const [drawer, setDrawer] = useState<Json | null>(null)
  const [version, setVersion] = useState(0)
  const [preset, setPreset] = useState<{ id: string; nonce: number } | undefined>()
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [m, g, t] = await Promise.all([
        get(`/api/meta?tenant=${tenant}`),
        get(`/api/graph?tenant=${tenant}`),
        get(`/api/targets?tenant=${tenant}`),
      ])
      setMeta(m)
      setGraph(g)
      setTargets(t)
      setVersion((v) => v + 1)
      setError('')
    } catch (e) {
      setError(`Backend not reachable (${e}). Start it with: python run.py`)
    }
  }, [tenant])

  useEffect(() => {
    refresh()
    setHl(emptyHighlight())
    setDrawer(null)
  }, [refresh])

  const trace = (nodes: string[], edges: string[][], reset = false) => {
    setHl((h) => {
      const base = reset || h.mode !== 'trace' ? emptyHighlight() : h
      return {
        ...base,
        mode: 'trace',
        nodes: new Set([...base.nodes, ...nodes]),
        edges: new Set([...base.edges, ...edges.map(([a, b]) => edgeKey(a, b))]),
      }
    })
    setFocusKey((k) => k + 1)
  }

  const cascade = (cas: Json | null) => {
    if (!cas) {
      setHl(emptyHighlight())
      return
    }
    const invalid = new Set<string>(cas.invalidated.map((c: Json) => c.id))
    const survived = new Set<string>(cas.survived.map((c: Json) => c.id))
    const nodes = new Set<string>([cas.target.id, ...invalid, ...survived])
    cas.survived.forEach((c: Json) => c.support_path.forEach((id: string) => nodes.add(id)))
    cas.decisions_at_risk.forEach((d: Json) => nodes.add(d.id))
    cas.decisions_weakened.forEach((d: Json) => nodes.add(d.id))
    cas.owners.forEach((o: Json) => nodes.add(o.id))
    setHl({ mode: 'cascade', nodes, invalid, survived, edges: new Set(cas.edges.map(([a, b]: string[]) => edgeKey(a, b))), target: cas.target.id })
    setFocusKey((k) => k + 1)
  }

  const openNode = async (id: string) => {
    try {
      const d = await get(`/api/node/${encodeURIComponent(id)}?tenant=${tenant}`)
      setDrawer(d)
    } catch (e) {
      setDrawer({ kind: 'Error', result: String(e), nodes: [], edges: [] })
    }
  }

  const previewFromAnywhere = (id: string) => {
    setTab('Retract')
    setPreset({ id, nonce: Date.now() })
  }

  const reset = async () => {
    if (!confirm(`Reload the ${tenant} demo graph? All changes, answers and actions are discarded.`)) return
    await post('/api/reset', { tenant })
    setHl(emptyHighlight())
    setDrawer(null)
    refresh()
  }

  return (
    <div className="app">
      <header>
        <a className="brand" href="#/">
          <span className="logo">
            <span className="logo-dot">R</span>
            Retract
          </span>
        </a>
        <div className="status-strip">
          {meta &&
            Object.entries(meta.status as Record<string, number>).map(([s, n]) => (
              <span key={s} className="pill" style={{ borderColor: STATUS_COLOR[s], color: STATUS_COLOR[s] }}>
                {n} {s.toLowerCase()}
              </span>
            ))}
        </div>
        <div className="controls">
          <span className={`mode ${meta?.llm ? 'llm' : ''}`} title="LLM used for extraction and phrasing. Outcomes are always computed from the graph.">
            {meta?.llm ? meta.llm : 'offline'}
          </span>
          <select value={tenant} onChange={(e) => setTenant(e.target.value)} title="Each tenant is its own FalkorDB graph">
            {(meta?.tenants ?? ['northwind']).filter((t: string) => !t.startsWith('eval') && !t.startsWith('test')).map((t: string) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <button className="ghost small" onClick={reset} title="Reload the demo graph">
            Reset
          </button>
        </div>
      </header>
      {error && <div className="banner">{error}</div>}
      <main>
        <section className="left">
          <Chat tenant={tenant} people={targets.people} onStep={trace} onAnswer={(n, e) => trace(n, e)} onNodeClick={openNode} onDone={refresh} />
        </section>
        <section className="center">
          <GraphView nodes={graph.nodes} links={graph.links} highlight={hl} focusKey={focusKey} onNodeClick={openNode} selected={drawer?.result?.claim?.id ?? drawer?.result?.source?.id ?? drawer?.result?.decision?.id} />
          {hl.mode !== 'none' && (
            <div className="hl-info">
              {hl.mode === 'cascade' ? (
                <>
                  <b>Cascade</b> from {hl.target}: <span className="red">{hl.invalid.size} lose support</span> ·{' '}
                  <span className="green">{hl.survived.size} survive</span>
                </>
              ) : (
                <>
                  <b>Traversal</b>: {hl.nodes.size} nodes touched by graph tools
                </>
              )}
              <button className="ghost small" onClick={() => setHl(emptyHighlight())}>
                clear
              </button>
            </div>
          )}
          <NodeDrawer
            data={drawer}
            onClose={() => setDrawer(null)}
            onNodeClick={openNode}
            onPreview={previewFromAnywhere}
            onHighlight={(n, e) => trace(n, e, true)}
          />
        </section>
        <section className="right">
          <nav className="tabs">
            {TABS.map((t) => (
              <button key={t} className={tab === t ? 'on' : ''} onClick={() => setTab(t)}>
                {t}
              </button>
            ))}
          </nav>
          <div className="tab-body">
            <div style={{ display: tab === 'Retract' ? 'block' : 'none' }}>
              <RetractPanel tenant={tenant} targets={targets} preset={preset} onCascade={cascade} onChanged={refresh} onNodeClick={openNode} />
            </div>
            {tab === 'Ingest' && (
              <IngestPanel tenant={tenant} people={targets.people} onChanged={refresh} onHighlight={(ids) => trace(ids, [], true)} onNodeClick={openNode} />
            )}
            {tab === 'Insights' && <InsightsPanel tenant={tenant} version={version} onNodeClick={openNode} onPreview={previewFromAnywhere} />}
            {tab === 'Memory' && <MemoryPanel tenant={tenant} version={version} onNodeClick={openNode} onChanged={refresh} />}
            {tab === 'Eval' && <EvalPanel />}
          </div>
        </section>
      </main>
    </div>
  )
}
