/* eslint-disable @typescript-eslint/no-explicit-any */
export type Json = any

async function req(path: string, init?: RequestInit): Promise<Json> {
  const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...init })
  const body = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(body?.detail ?? `${r.status} ${r.statusText}`)
  return body
}

export const get = (path: string) => req(path)
export const post = (path: string, data: Json) => req(path, { method: 'POST', body: JSON.stringify(data) })

/** POST that streams server-sent events; calls onEvent for every `data:` line. */
export async function stream(path: string, data: Json, onEvent: (e: Json) => void): Promise<void> {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!r.ok || !r.body) throw new Error(`${r.status} ${r.statusText}`)
  const reader = r.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let i
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, i)
      buf = buf.slice(i + 2)
      const line = chunk.split('\n').find((l) => l.startsWith('data: '))
      if (line) onEvent(JSON.parse(line.slice(6)))
    }
  }
}
