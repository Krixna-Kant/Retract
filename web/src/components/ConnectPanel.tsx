import { useEffect, useState } from 'react'
import type { Json } from '../api'
import { get, post } from '../api'

type Props = { onImported: (tenant: string) => void }

export default function ConnectPanel({ onImported }: Props) {
  const [name, setName] = useState('acme')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [mcp, setMcp] = useState<Json | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    get('/api/mcp').then(setMcp).catch(() => setMcp({ tools: [], config: {}, error: 'unavailable' }))
  }, [])

  const loadTemplate = async () => setText(JSON.stringify(await get('/api/template'), null, 2))

  const onFile = async (f?: File) => {
    if (!f) return
    setText(await f.text())
    const base = f.name.replace(/\.json$/i, '').toLowerCase().replace(/[^a-z0-9_]/g, '_').slice(0, 40)
    if (base) setName(base)
  }

  const doImport = async () => {
    setMsg(null)
    let data: Json
    try {
      data = JSON.parse(text)
    } catch {
      setMsg({ ok: false, text: 'Not valid JSON' })
      return
    }
    setBusy(true)
    try {
      const r = await post('/api/import', { tenant: name, data })
      const counts = Object.entries(r.claim_status as Record<string, number>).map(([k, v]) => `${v} ${k.toLowerCase()}`).join(' · ')
      setMsg({ ok: true, text: `Loaded into ${r.tenant}: ${counts}` })
      onImported(r.tenant)
    } catch (e) {
      setMsg({ ok: false, text: String(e).replace(/^Error: /, '') })
    } finally {
      setBusy(false)
    }
  }

  const config = mcp ? JSON.stringify(mcp.config, null, 2) : ''
  const copy = async () => {
    await navigator.clipboard.writeText(config)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="panel">
      <h3>Your data</h3>
      <div className="row">
        <input value={name} onChange={(e) => setName(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))} placeholder="company" style={{ flex: 1 }} />
        <label className="file-btn">
          JSON file
          <input type="file" accept=".json,application/json" onChange={(e) => onFile(e.target.files?.[0])} />
        </label>
        <button className="ghost small" onClick={loadTemplate}>Template</button>
      </div>
      <textarea rows={7} value={text} onChange={(e) => setText(e.target.value)} placeholder="people, systems, sources, claims, decisions and their links" spellCheck={false} className="mono" />
      <div className="row">
        <button className="primary" onClick={doImport} disabled={busy || !text.trim() || !name}>
          {busy ? 'Loading…' : 'Import'}
        </button>
        {msg && <span className={msg.ok ? 'green' : 'red'}>{msg.text}</span>}
      </div>

      <h3>Any agent, over MCP</h3>
      <div className="code-card">
        <button className="ghost small copy" onClick={copy}>{copied ? 'Copied' : 'Copy'}</button>
        <pre>{config}</pre>
      </div>
      {mcp?.error && <div className="error">{mcp.error}</div>}
      <div className="tool-chips">
        {(mcp?.tools ?? []).map((t: Json) => (
          <span key={t.name} className="badge blue" title={t.description}>{t.name}</span>
        ))}
      </div>
    </div>
  )
}
