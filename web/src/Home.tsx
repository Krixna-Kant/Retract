import { useEffect } from 'react'
import type { ReactNode } from 'react'

const INK = '#22223b'
const RED = '#e5484d'
const GREEN = '#3fa66b'
const YELLOW = '#f6c945'

function Rough() {
  return (
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden>
      <filter id="rough">
        <feTurbulence type="fractalNoise" baseFrequency="0.03" numOctaves="2" seed="3" />
        <feDisplacementMap in="SourceGraphic" scale="3" />
      </filter>
    </svg>
  )
}

function Doc({ x, y, label, fill, crossed }: { x: number; y: number; label: string; fill: string; crossed?: boolean }) {
  return (
    <g>
      <rect x={x} y={y} width="78" height="92" rx="6" fill={fill} stroke={INK} strokeWidth="2.5" />
      {[22, 36, 50, 64].map((d) => (
        <line key={d} x1={x + 14} y1={y + d} x2={x + (d === 64 ? 44 : 64)} y2={y + d} stroke={INK} strokeWidth="2" strokeLinecap="round" opacity=".55" />
      ))}
      <text x={x + 39} y={y + 116} textAnchor="middle" className="sk-label">{label}</text>
      {crossed && (
        <g stroke={RED} strokeWidth="5" strokeLinecap="round">
          <line x1={x - 10} y1={y - 8} x2={x + 88} y2={y + 100} />
          <line x1={x + 88} y1={y - 8} x2={x - 10} y2={y + 100} />
        </g>
      )}
    </g>
  )
}

function Node({ x, y, color, dead }: { x: number; y: number; color: string; dead?: boolean }) {
  return (
    <g opacity={dead ? 0.85 : 1}>
      <circle cx={x} cy={y} r="17" fill={color} stroke={INK} strokeWidth="2.5" />
      {dead && <path d={`M${x - 11} ${y - 4} q6 6 11 0 t11 2 M${x - 10} ${y + 5} q6 -5 10 0 t11 -1`} stroke={INK} strokeWidth="2" fill="none" />}
    </g>
  )
}

function Hero() {
  const memo = { x: 40, y: 40 }
  const adr = { x: 40, y: 250 }
  const claims = [
    { x: 250, y: 70, dead: true },
    { x: 300, y: 150, dead: true },
    { x: 250, y: 230, dead: false },
    { x: 330, y: 300, dead: false },
  ]
  return (
    <svg viewBox="0 0 480 420" className="hero-art">
      <g filter="url(#rough)">
        {claims.map((c, i) => (
          <path key={`m${i}`} d={`M${c.x - 17} ${c.y} Q ${180} ${c.y - 30} ${memo.x + 82} ${memo.y + 46}`} stroke={RED} strokeWidth="2.5" fill="none" strokeDasharray="7 6" />
        ))}
        {claims.slice(2).map((c, i) => (
          <path key={`a${i}`} d={`M${c.x - 17} ${c.y} Q ${170} ${c.y + 30} ${adr.x + 82} ${adr.y + 46}`} stroke={GREEN} strokeWidth="3" fill="none" />
        ))}
        <Doc {...memo} label="memo" fill="#fff8d6" crossed />
        <Doc {...adr} label="ADR" fill="#e6f4ff" />
        {claims.map((c, i) => (
          <Node key={i} x={c.x} y={c.y} color={c.dead ? '#f9c6c6' : '#c9f2c7'} dead={c.dead} />
        ))}
        <g>
          <circle cx="420" cy="120" r="16" fill="#ffd9e6" stroke={INK} strokeWidth="2.5" />
          <path d="M396 168 q24 -36 48 0" fill="#ffd9e6" stroke={INK} strokeWidth="2.5" />
          <path d="M318 150 C 360 140, 380 135, 398 128" stroke={INK} strokeWidth="2" fill="none" strokeDasharray="3 5" />
          <path d="M440 92 l10 -10 M446 104 l14 -4 M432 86 l2 -14" stroke={YELLOW} strokeWidth="3.5" strokeLinecap="round" />
        </g>
      </g>
    </svg>
  )
}

const S = { stroke: INK, strokeWidth: 2.5 }

function Paper({ x, y, fill, w = 46, h = 56 }: { x: number; y: number; fill: string; w?: number; h?: number }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx="5" fill={fill} {...S} />
      {[14, 24, 34].map((d) => (
        <line key={d} x1={x + 9} y1={y + d} x2={x + w - 10} y2={y + d} stroke={INK} strokeWidth="1.8" opacity=".45" strokeLinecap="round" />
      ))}
    </g>
  )
}

function Dot({ x, y, fill, r = 14, dead }: { x: number; y: number; fill: string; r?: number; dead?: boolean }) {
  return (
    <g>
      <circle cx={x} cy={y} r={r} fill={fill} {...S} />
      {dead && <path d={`M${x - 8} ${y - 3} q4 5 8 0 t8 1 M${x - 7} ${y + 4} q4 -4 7 0 t8 -1`} stroke={INK} strokeWidth="1.8" fill="none" />}
    </g>
  )
}

const Arrow = ({ d, color = INK, dash }: { d: string; color?: string; dash?: boolean }) => (
  <path d={d} stroke={color} strokeWidth="2.5" fill="none" strokeLinecap="round" strokeDasharray={dash ? '6 6' : undefined} markerEnd={`url(#tip-${color.slice(1)})`} />
)

function Art({ children }: { children: ReactNode }) {
  return (
    <svg viewBox="0 0 300 180" className="story-art">
      <defs>
        {[INK, RED, GREEN].map((c) => (
          <marker key={c} id={`tip-${c.slice(1)}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M1 1 L9 5 L1 9" fill="none" stroke={c} strokeWidth="1.8" strokeLinecap="round" />
          </marker>
        ))}
      </defs>
      <g filter="url(#rough)">{children}</g>
    </svg>
  )
}

const ArtLinks = () => (
  <Art>
    <Paper x={34} y={22} fill="#fff8d6" />
    <Paper x={34} y={104} fill="#e6f4ff" />
    <Arrow d="M216 40 Q 150 30 86 48" />
    <Arrow d="M212 92 Q 150 80 86 56" />
    <Arrow d="M212 98 Q 150 120 86 130" />
    <Arrow d="M216 148 Q 150 150 86 136" />
    <Dot x={232} y={40} fill="#dbe7ff" />
    <Dot x={228} y={96} fill="#c9f2c7" />
    <Dot x={232} y={150} fill="#dbe7ff" />
  </Art>
)

const ArtRetracted = () => (
  <Art>
    <Paper x={110} y={34} fill="#fff8d6" w={80} h={100} />
    <g transform="rotate(-14 150 92)">
      <rect x="86" y="72" width="128" height="40" rx="6" fill="none" stroke={RED} strokeWidth="3.5" />
      <text x="150" y="101" textAnchor="middle" className="stamp">RETRACTED</text>
    </g>
  </Art>
)

const ArtCascade = () => (
  <Art>
    <Paper x={14} y={62} fill="#fff8d6" />
    <path d="M8 56 L66 124 M66 56 L8 124" stroke={RED} strokeWidth="4" strokeLinecap="round" />
    <Arrow d="M96 90 H 70" color={RED} dash />
    <Dot x={112} y={90} fill="#f9c6c6" dead />
    <Arrow d="M168 90 H 130" color={RED} dash />
    <Dot x={184} y={90} fill="#f9c6c6" dead />
    <Arrow d="M238 90 H 202" color={RED} dash />
    <path d="M262 64 L288 90 L262 116 L236 90 Z" fill="#efe9ff" stroke={RED} strokeWidth="3" />
  </Art>
)

const ArtSurvive = () => (
  <Art>
    <g opacity=".35"><Paper x={20} y={14} fill="#fff8d6" /></g>
    <Paper x={20} y={110} fill="#e6f4ff" />
    <Arrow d="M108 70 Q 90 50 70 46" color={RED} dash />
    <Arrow d="M108 84 Q 90 120 70 132" color={GREEN} />
    <Dot x={124} y={78} fill="#c9f2c7" />
    <path d="M117 78 l5 6 l9 -12" stroke={INK} strokeWidth="2.5" fill="none" strokeLinecap="round" />
    <Dot x={222} y={58} fill="#f9c6c6" dead />
    <Dot x={252} y={122} fill="#f9c6c6" dead />
    <Arrow d="M232 70 Q 262 84 254 106" color={RED} />
    <Arrow d="M242 118 Q 210 104 218 74" color={RED} />
  </Art>
)

const ArtApprove = () => (
  <Art>
    <rect x="60" y="20" width="180" height="140" rx="10" fill="#fffdf8" {...S} />
    <line x1="80" y1="46" x2="190" y2="46" stroke={INK} strokeWidth="2.5" strokeLinecap="round" />
    <line x1="80" y1="66" x2="214" y2="66" stroke={INK} strokeWidth="1.8" opacity=".45" strokeLinecap="round" />
    <line x1="80" y1="82" x2="170" y2="82" stroke={INK} strokeWidth="1.8" opacity=".45" strokeLinecap="round" />
    <rect x="80" y="110" width="66" height="30" rx="12" fill="#c9f2c7" {...S} />
    <path d="M102 125 l7 7 l14 -14" stroke={INK} strokeWidth="2.5" fill="none" strokeLinecap="round" />
    <rect x="156" y="110" width="66" height="30" rx="12" fill="#fde0e0" {...S} />
    <path d="M181 118 l16 14 M197 118 l-16 14" stroke={INK} strokeWidth="2.5" strokeLinecap="round" />
  </Art>
)

const ArtNotify = () => (
  <Art>
    <circle cx="232" cy="66" r="20" fill="#ffd9e6" {...S} />
    <path d="M200 128 q32 -50 64 0" fill="#ffd9e6" {...S} />
    <path d="M70 120 C 110 70, 150 150, 196 92" stroke={INK} strokeWidth="2" fill="none" strokeDasharray="3 6" />
    <g transform="rotate(-10 60 120)">
      <rect x="30" y="104" width="62" height="40" rx="4" fill="#fff8d6" {...S} />
      <path d="M30 106 L61 128 L92 106" fill="none" {...S} />
    </g>
    <path d="M258 40 l10 -10 M264 52 l14 -4 M250 34 l2 -14" stroke={YELLOW} strokeWidth="3.5" strokeLinecap="round" />
  </Art>
)

const ArtAnswers = () => (
  <Art>
    {[
      ['answer + path', '#c9f2c7', 14],
      ['stale', '#fde0e0', 56],
      ['contested', '#fff3c4', 98],
      ['unknown', '#ecebef', 140],
    ].map(([t, f, y], i) => (
      <g key={t as string} transform={`rotate(${[-2, 1.5, -1, 2][i]} 150 ${(y as number) + 13})`}>
        <rect x={[54, 76, 64, 84][i]} y={y as number} width="172" height="28" rx="13" fill={f as string} {...S} />
        <text x={[140, 162, 150, 170][i]} y={(y as number) + 20} textAnchor="middle" className="tag-text">{t}</text>
      </g>
    ))}
  </Art>
)

const STORY = [
  { art: <ArtLinks />, title: 'Every claim has a reason', line: 'Each fact an agent remembers is linked to the sources it came from.' },
  { art: <ArtRetracted />, title: 'Then a source turns out wrong', line: 'A memo is retracted, or a decision is reversed.' },
  { art: <ArtCascade />, title: 'The graph follows the damage', line: 'FalkorDB walks the links to everything that leaned on it.' },
  { art: <ArtSurvive />, title: 'What still stands, stays', line: 'Claims with another real source survive. Loops never count as proof.' },
  { art: <ArtApprove />, title: 'Nothing changes without a yes', line: 'You see the whole cascade first. One approval applies it, one click rolls it back.' },
  { art: <ArtNotify />, title: 'The right people hear', line: 'Owners of every affected system and decision get a drafted note.' },
  { art: <ArtAnswers />, title: 'Answers stay honest', line: 'Every answer shows its path, or says it is stale, contested or unknown.' },
]

function useReveal() {
  useEffect(() => {
    const els = document.querySelectorAll('.reveal')
    const io = new IntersectionObserver(
      (es) => es.forEach((e) => e.isIntersecting && e.target.classList.add('in')),
      { threshold: 0.2 },
    )
    els.forEach((el) => io.observe(el))
    return () => io.disconnect()
  }, [])
}

const NUMBERS = [
  { n: '16/16', l: 'cascades exact' },
  { n: '1', l: 'Cypher query' },
  { n: '0', l: 'LLM-written queries' },
]

export default function Home() {
  useReveal()
  return (
    <div className="home">
      <Rough />
      <nav className="sk-nav sk-box">
        <a className="brand-mark" href="#/">
          <span className="logo-dot">R</span>
          Retract
        </a>
        <div className="nav-links">
          <a href="#how" onClick={(e) => { e.preventDefault(); document.getElementById('how')?.scrollIntoView({ behavior: 'smooth' }) }}>How it works</a>
          <a href="#numbers" onClick={(e) => { e.preventDefault(); document.getElementById('numbers')?.scrollIntoView({ behavior: 'smooth' }) }}>Results</a>
        </div>
        <a className="sk-btn primary" href="#/app">Open demo</a>
      </nav>

      <section className="hero">
        <div className="hero-text reveal">
          <span className="sk-badge">Built on FalkorDB</span>
          <h1>
            Memory that knows <br />what to <span className="ink-blue">forget.</span>
          </h1>
          <p className="lede">When a source turns out wrong, Retract finds everything built on it and keeps what still stands.</p>
          <div className="hero-cta">
            <a className="sk-btn primary big" href="#/app">Try the demo</a>
          </div>
        </div>
        <div className="hero-card">
          <div className="paper back" />
          <div className="paper front">
            <Hero />
          </div>
        </div>
      </section>

      <section id="how" className="story">
        <h2 className="section-title reveal">How it works</h2>
        {STORY.map((s, i) => (
          <div key={s.title} className={`story-row reveal ${i % 2 ? 'flip' : ''}`}>
            <div className="story-card" style={{ transform: `rotate(${[-1.4, 1.2, -0.8, 1, -1.2, 0.9, -0.7][i]}deg)` }}>
              {s.art}
            </div>
            <div className="story-text">
              <span className="step-num">{i + 1}</span>
              <h3>{s.title}</h3>
              <p>{s.line}</p>
            </div>
          </div>
        ))}
      </section>

      <section className="story">
        <h2 className="section-title reveal">Bring your own</h2>
        <div className="byo">
          <a className="byo-card reveal" href="#/app/connect">
            <svg viewBox="0 0 120 70" className="byo-art">
              <g filter="url(#rough)">
                <rect x="8" y="10" width="40" height="50" rx="5" fill="#e6f4ff" stroke={INK} strokeWidth="2.5" />
                <path d="M18 24 H38 M18 34 H38 M18 44 H30" stroke={INK} strokeWidth="2" strokeLinecap="round" opacity=".5" />
                <path d="M56 35 H 78" stroke={INK} strokeWidth="2.5" strokeLinecap="round" />
                <path d="M72 29 L79 35 L72 41" stroke={INK} strokeWidth="2.5" fill="none" strokeLinecap="round" />
                <circle cx="96" cy="22" r="8" fill="#c9f2c7" stroke={INK} strokeWidth="2.2" />
                <circle cx="104" cy="48" r="8" fill="#fff3c4" stroke={INK} strokeWidth="2.2" />
                <circle cx="86" cy="50" r="6" fill="#ffd9e6" stroke={INK} strokeWidth="2.2" />
                <path d="M96 30 L102 40 M92 29 L88 44" stroke={INK} strokeWidth="1.8" />
              </g>
            </svg>
            <h3>Your company</h3>
            <p>Import your people, systems and docs into a graph of their own.</p>
            <code>python -m data.load my_company.json acme</code>
          </a>
          <a className="byo-card reveal" href="#/app/connect">
            <svg viewBox="0 0 120 70" className="byo-art">
              <g filter="url(#rough)">
                <rect x="8" y="16" width="44" height="38" rx="8" fill="#efe9ff" stroke={INK} strokeWidth="2.5" />
                <circle cx="22" cy="33" r="3" fill={INK} />
                <circle cx="38" cy="33" r="3" fill={INK} />
                <path d="M22 44 q8 5 16 0" stroke={INK} strokeWidth="2" fill="none" strokeLinecap="round" />
                <path d="M30 16 V 8" stroke={INK} strokeWidth="2.5" strokeLinecap="round" />
                <path d="M58 30 H 74 M58 40 H 74" stroke={INK} strokeWidth="2.5" strokeLinecap="round" />
                <rect x="78" y="14" width="34" height="42" rx="5" fill="#fff8d6" stroke={INK} strokeWidth="2.5" />
                <path d="M86 26 H104 M86 35 H104 M86 44 H98" stroke={INK} strokeWidth="2" strokeLinecap="round" opacity=".5" />
              </g>
            </svg>
            <h3>Any agent</h3>
            <p>Claude, Cursor or your own agent can use every graph tool over MCP.</p>
            <code>python -m retract.mcp_server</code>
          </a>
        </div>
      </section>

      <section id="numbers" className="numbers reveal">
        {NUMBERS.map((x) => (
          <div key={x.l} className="num-box">
            <b>{x.n}</b>
            <span>{x.l}</span>
          </div>
        ))}
      </section>

      <section className="closing reveal">
        <a className="sk-btn primary big" href="#/app">Open the demo</a>
      </section>

      <footer className="home-foot">
        <span>Retract · FalkorDB Graph Hacks 2026</span>
        <span className="foot-links">
          <span>Krishna Kant</span>
          <a href="https://x.com/krixna01" target="_blank" rel="noopener noreferrer" title="X">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden><path d="M4 4 L20 20 M20 4 L4 20" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" /></svg>
            X
          </a>
          <a href="https://krixna-kant.github.io/portfolio/" target="_blank" rel="noopener noreferrer" title="Portfolio">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="9" /><path d="M3 12 H21 M12 3 C 7 8, 7 16, 12 21 M12 3 C 17 8, 17 16, 12 21" /></svg>
            Portfolio
          </a>
        </span>
      </footer>
    </div>
  )
}
