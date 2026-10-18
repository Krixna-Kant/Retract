export type GNode = {
  id: string
  label: string
  name: string
  status?: string
  kind?: string
  trust?: number
  revoked?: boolean
  quarantined?: boolean
  team?: string
  x?: number
  y?: number
}

export type GLink = {
  source: string | GNode
  target: string | GNode
  type: string
}

export type Highlight = {
  mode: 'none' | 'trace' | 'cascade'
  nodes: Set<string>
  edges: Set<string>
  invalid: Set<string>
  survived: Set<string>
  target?: string
  focus?: string
}

export const emptyHighlight = (): Highlight => ({
  mode: 'none',
  nodes: new Set(),
  edges: new Set(),
  invalid: new Set(),
  survived: new Set(),
})

export const edgeKey = (a: string, b: string) => `${a}->${b}`

export const OUTCOME_COLOR: Record<string, string> = {
  ANSWER_WITH_PATH: '#34d399',
  STALE: '#f87171',
  CONTESTED: '#fbbf24',
  UNKNOWN_NO_PATH: '#94a3b8',
}

export const OUTCOME_HELP: Record<string, string> = {
  ANSWER_WITH_PATH: 'A relevant claim has a live support path to a source or active decision',
  STALE: 'The claims that answered this lost their support',
  CONTESTED: 'Live claims disagree; both are kept and shown',
  UNKNOWN_NO_PATH: 'Nothing in memory supports an answer, so the agent does not guess',
}

export const STATUS_COLOR: Record<string, string> = {
  CONFIRMED: '#2dd4bf',
  PROPOSED: '#60a5fa',
  CONTESTED: '#fbbf24',
  INVALIDATED: '#ef4444',
  SUPERSEDED: '#8b8fa8',
  QUARANTINED: '#e879f9',
}

export const LABEL_COLOR: Record<string, string> = {
  Source: '#f59e0b',
  Decision: '#a78bfa',
  Person: '#f472b6',
  System: '#22d3ee',
  Team: '#64748b',
  Answer: '#cbd5e1',
}
