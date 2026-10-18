"""Three agents share one graph: ingest writes claims, auditor maintains status, answer reads."""
AGENTS = [
    {"id": "agent:ingest", "role": "Reads a source, writes PROPOSED claims with DERIVED_FROM edges"},
    {"id": "agent:auditor", "role": "Confirms corroborated claims, marks contradictions CONTESTED"},
    {"id": "agent:answer", "role": "Answers questions with fixed graph tools; records answers as episodic memory"},
]
