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
  ANSWER_WITH_PATH: '#3fa66b',
  STALE: '#e5484d',
  CONTESTED: '#d9961a',
  UNKNOWN_NO_PATH: '#6b6b80',
}

export const OUTCOME_HELP: Record<string, string> = {
  ANSWER_WITH_PATH: 'A relevant claim has a live support path to a source or active decision',
  STALE: 'The claims that answered this lost their support',
  CONTESTED: 'Live claims disagree; both are kept and shown',
  UNKNOWN_NO_PATH: 'Nothing in memory supports an answer, so the agent does not guess',
}

export const STATUS_COLOR: Record<string, string> = {
  CONFIRMED: '#3fa66b',
  PROPOSED: '#4a7bd0',
  CONTESTED: '#e0a21b',
  INVALIDATED: '#e5484d',
  SUPERSEDED: '#a3a3b2',
  QUARANTINED: '#c457c9',
}

export const LABEL_COLOR: Record<string, string> = {
  Source: '#f6c945',
  Decision: '#a58ff0',
  Person: '#f39bbf',
  System: '#7fd3df',
  Team: '#a3a3b2',
  Answer: '#d9d4c7',
}
