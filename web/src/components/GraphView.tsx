import { useEffect, useMemo, useRef, useState } from 'react'
import { forceX, forceY } from 'd3-force'
import ForceGraph2D from 'react-force-graph-2d'
import type { GLink, GNode, Highlight } from '../types'
import { LABEL_COLOR, STATUS_COLOR, edgeKey } from '../types'

type Props = {
  nodes: GNode[]
  links: GLink[]
  highlight: Highlight
  focusKey: number
  onNodeClick: (id: string) => void
  selected?: string
}

const SIZE: Record<string, number> = { Claim: 4, Source: 5.5, Decision: 6, System: 7, Person: 4.2, Team: 6, Answer: 3 }
const LINK_COLOR: Record<string, string> = {
  DERIVED_FROM: 'rgba(148,163,184,0.22)',
  SUPPORTED_BY: 'rgba(167,139,250,0.25)',
  SUPERSEDES: 'rgba(167,139,250,0.7)',
  CONTRADICTS: 'rgba(251,191,36,0.75)',
  ABOUT: 'rgba(34,211,238,0.10)',
  OWNS: 'rgba(244,114,182,0.14)',
  AUTHORED: 'rgba(245,158,11,0.10)',
  MEMBER_OF: 'rgba(100,116,139,0.10)',
  CITED: 'rgba(203,213,225,0.18)',
  RECORDED_IN: 'rgba(167,139,250,0.18)',
  ASKED: 'rgba(203,213,225,0.10)',
}
const ALL_LABELS = ['Claim', 'Source', 'Decision', 'System', 'Person', 'Team', 'Answer']

const idOf = (x: string | GNode) => (typeof x === 'string' ? x : x.id)

function shape(ctx: CanvasRenderingContext2D, label: string, x: number, y: number, r: number) {
  ctx.beginPath()
  if (label === 'Source') {
    ctx.rect(x - r, y - r, 2 * r, 2 * r)
  } else if (label === 'Decision') {
    ctx.moveTo(x, y - r * 1.25)
    ctx.lineTo(x + r * 1.25, y)
    ctx.lineTo(x, y + r * 1.25)
    ctx.lineTo(x - r * 1.25, y)
    ctx.closePath()
  } else if (label === 'System') {
    for (let i = 0; i < 6; i++) {
      const a = (Math.PI / 3) * i + Math.PI / 6
      const px = x + r * Math.cos(a)
      const py = y + r * Math.sin(a)
      if (i === 0) ctx.moveTo(px, py)
      else ctx.lineTo(px, py)
    }
    ctx.closePath()
  } else {
    ctx.arc(x, y, r, 0, 2 * Math.PI)
  }
}

export default function GraphView({ nodes, links, highlight, focusKey, onNodeClick, selected }: Props) {
  const wrap = useRef<HTMLDivElement>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fg = useRef<any>(undefined)
  const [size, setSize] = useState({ w: 800, h: 600 })
  const [show, setShow] = useState<Set<string>>(new Set(['Claim', 'Source', 'Decision', 'System', 'Person']))
  const cache = useRef(new Map<string, GNode>())

  useEffect(() => {
    if (!wrap.current) return
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }))
    ro.observe(wrap.current)
    return () => ro.disconnect()
  }, [])

  const data = useMemo(() => {
    const keep = new Map<string, GNode>()
    for (const n of nodes) {
      if (!show.has(n.label)) continue
      const old = cache.current.get(n.id)
      const merged = old ? Object.assign(old, n) : { ...n }
      keep.set(n.id, merged)
    }
    cache.current = new Map([...cache.current, ...keep])
    const ls = links
      .filter((l) => keep.has(idOf(l.source)) && keep.has(idOf(l.target)))
      .map((l) => ({ source: idOf(l.source), target: idOf(l.target), type: l.type }))
    return { nodes: [...keep.values()], links: ls }
  }, [nodes, links, show])

  useEffect(() => {
    if (!fg.current) return
    fg.current.d3Force('charge')?.strength(-34).distanceMax(260)
    fg.current.d3Force('x', forceX(0).strength(0.045))
    fg.current.d3Force('y', forceY(0).strength(0.045))
    fg.current.d3Force('link')?.distance((l: GLink) => (l.type === 'DERIVED_FROM' ? 26 : l.type === 'ABOUT' ? 60 : 40))
  }, [data])

  useEffect(() => {
    if (!fg.current || highlight.nodes.size === 0) return
    const t = setTimeout(() => {
      const ids = new Set([...highlight.nodes, ...highlight.invalid, ...highlight.survived])
      const pts = data.nodes.filter((n) => ids.has(n.id) && n.x !== undefined)
      if (!pts.length) return
      const xs = pts.map((n) => n.x as number)
      const ys = pts.map((n) => n.y as number)
      const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
      const k = Math.min(1.8, Math.max(0.5, Math.min(size.w / (x1 - x0 + 160), size.h / (y1 - y0 + 160))))
      fg.current?.centerAt((x0 + x1) / 2, (y0 + y1) / 2, 700)
      fg.current?.zoom(k, 700)
    }, 250)
    return () => clearTimeout(t)
  }, [focusKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const active = highlight.mode !== 'none'
  const edgeOn = (l: GLink) => {
    const a = idOf(l.source)
    const b = idOf(l.target)
    return highlight.edges.has(edgeKey(a, b)) || highlight.edges.has(edgeKey(b, a))
  }
  const edgeColor = (l: GLink) => {
    const a = idOf(l.source)
    if (highlight.mode === 'cascade') return highlight.survived.has(a) && !highlight.invalid.has(a) ? '#34d399' : '#f87171'
    return '#facc15'
  }

  return (
    <div className="graph-wrap" ref={wrap}>
      <ForceGraph2D
        ref={fg}
        width={size.w}
        height={size.h}
        graphData={data}
        backgroundColor="rgba(0,0,0,0)"
        cooldownTicks={180}
        warmupTicks={40}
        nodeRelSize={4}
        nodeLabel={(n: GNode) =>
          `<div class="tip"><b>${n.label} · ${n.id}</b>${n.status ? ` <i>${n.status}</i>` : ''}<br/>${(n.name ?? '').slice(0, 140)}</div>`
        }
        onNodeClick={(n: GNode) => onNodeClick(n.id)}
        linkColor={(l: GLink) => (edgeOn(l) ? edgeColor(l) : active ? 'rgba(148,163,184,0.06)' : LINK_COLOR[l.type] ?? '#334')}
        linkWidth={(l: GLink) => (edgeOn(l) ? 2.4 : l.type === 'SUPERSEDES' || l.type === 'CONTRADICTS' ? 1.4 : 0.6)}
        linkLineDash={(l: GLink) => (l.type === 'CONTRADICTS' ? [3, 2] : null)}
        linkDirectionalArrowLength={(l: GLink) => (edgeOn(l) || l.type === 'SUPERSEDES' ? 4 : 0)}
        linkDirectionalArrowRelPos={0.9}
        linkDirectionalParticles={(l: GLink) => (edgeOn(l) ? 3 : 0)}
        linkDirectionalParticleWidth={2.4}
        linkDirectionalParticleSpeed={0.012}
        linkDirectionalParticleColor={(l: GLink) => edgeColor(l)}
        nodeCanvasObject={(n: GNode, ctx: CanvasRenderingContext2D, scale: number) => {
          const x = n.x ?? 0
          const y = n.y ?? 0
          const r = SIZE[n.label] ?? 4
          const on = highlight.nodes.has(n.id) || highlight.invalid.has(n.id) || highlight.survived.has(n.id)
          const dead = (n.label === 'Source' && (n.revoked || n.quarantined)) || ['INVALIDATED', 'SUPERSEDED', 'QUARANTINED', 'REVERSED'].includes(n.status ?? '')
          ctx.globalAlpha = active && !on && n.id !== selected ? 0.13 : dead ? 0.55 : 1
          if (on || n.id === selected) {
            const glow = highlight.invalid.has(n.id) ? '#ef4444' : highlight.survived.has(n.id) ? '#34d399' : n.id === highlight.target ? '#ffffff' : '#facc15'
            ctx.shadowColor = glow
            ctx.shadowBlur = 14
            shape(ctx, n.label, x, y, r + 2.6)
            ctx.strokeStyle = glow
            ctx.lineWidth = 1.8
            ctx.stroke()
            ctx.shadowBlur = 0
          }
          shape(ctx, n.label, x, y, r)
          ctx.fillStyle = n.label === 'Claim' ? STATUS_COLOR[n.status ?? 'PROPOSED'] ?? '#60a5fa' : n.label === 'Decision' && n.status !== 'ACTIVE' ? '#5b5675' : LABEL_COLOR[n.label] ?? '#999'
          if (n.label === 'Source' && n.trust !== undefined && n.trust < 0.3) ctx.fillStyle = '#fb7185'
          ctx.fill()
          if (dead && n.label === 'Source') {
            ctx.strokeStyle = '#ef4444'
            ctx.lineWidth = 1.4
            ctx.beginPath()
            ctx.moveTo(x - r, y - r)
            ctx.lineTo(x + r, y + r)
            ctx.moveTo(x + r, y - r)
            ctx.lineTo(x - r, y + r)
            ctx.stroke()
          }
          if (on || n.id === selected || scale > 2.6 || (n.label === 'System' && scale > 1.1)) {
            const text = n.label === 'Claim' || n.label === 'Source' || n.label === 'Decision' ? n.id : n.name
            const fs = Math.max(10 / scale, 2.2)
            ctx.font = `${on ? 600 : 400} ${fs}px Inter, system-ui, sans-serif`
            ctx.textAlign = 'center'
            ctx.textBaseline = 'top'
            ctx.fillStyle = on ? '#f8fafc' : 'rgba(226,232,240,0.75)'
            ctx.fillText(text, x, y + r + 2)
          }
          ctx.globalAlpha = 1
        }}
        nodePointerAreaPaint={(n: GNode, color: string, ctx: CanvasRenderingContext2D) => {
          ctx.fillStyle = color
          shape(ctx, n.label, n.x ?? 0, n.y ?? 0, (SIZE[n.label] ?? 4) + 2)
          ctx.fill()
        }}
      />
      <div className="graph-filters">
        {ALL_LABELS.map((l) => (
          <label key={l} className={show.has(l) ? 'on' : ''}>
            <input
              type="checkbox"
              checked={show.has(l)}
              onChange={() => {
                const s = new Set(show)
                if (s.has(l)) s.delete(l)
                else s.add(l)
                setShow(s)
              }}
            />
            {l}
          </label>
        ))}
        <button className="ghost small" onClick={() => fg.current?.zoomToFit(600, 40)}>Fit</button>
      </div>
      <div className="legend">
        <span><i className="dot" style={{ background: STATUS_COLOR.CONFIRMED }} />confirmed</span>
        <span><i className="dot" style={{ background: STATUS_COLOR.PROPOSED }} />proposed</span>
        <span><i className="dot" style={{ background: STATUS_COLOR.CONTESTED }} />contested</span>
        <span><i className="dot" style={{ background: STATUS_COLOR.INVALIDATED }} />invalidated</span>
        <span><i className="dot" style={{ background: STATUS_COLOR.SUPERSEDED }} />superseded</span>
        <span><i className="dot" style={{ background: STATUS_COLOR.QUARANTINED }} />quarantined</span>
        <span><i className="sq" style={{ background: LABEL_COLOR.Source }} />source</span>
        <span><i className="dia" style={{ background: LABEL_COLOR.Decision }} />decision</span>
        <span><i className="hex" style={{ background: LABEL_COLOR.System }} />system</span>
        <span><i className="dot" style={{ background: LABEL_COLOR.Person }} />person</span>
      </div>
    </div>
  )
}
