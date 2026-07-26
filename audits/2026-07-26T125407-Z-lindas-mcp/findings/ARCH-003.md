## Finding: ARCH-003 — «Not Found» Anti-Pattern: Heuristiken statt leerer Antworten

**Severity:** medium
**Status:** open
**Server:** lindas-mcp
**Check-Reference:** ARCH-003 (fail)
**PDF-Reference:** Sec 2.2

### Observed Behavior
`cube.search()` and `resolve_municipality()` return an empty list on no match; result models carry no `match_type` field and there is no fuzzy fallback, suggestion, or actionable note.

### Expected Behavior
Empty results should carry a `match_type` (exact/none) and an actionable next-step note (or a fuzzy/suggestion fallback), so the agent can distinguish a real miss from a malformed query and knows what to try next.

### Evidence
- src/lindas_mcp/lindas/cube.py — search() returns published[:limit] / empty list on no match, no fuzzy fallback and no suggestions
- cube.py — resolve_municipality() returns [] on no match with no fuzzy/suggestion mechanism
- models.py — CubeSearchResult/MunicipalityResult have no match_type field; grep for match_type|fuzzy|suggest returns NONE

### Gaps
- No match_type field (exact/fuzzy/none) on search results
- Empty results trigger neither a fuzzy-match nor a suggestion mechanism, and no actionable 'note' on empty results

### Risk Description
The agent gets a bare empty result and may hallucinate, retry blindly, or report 'no data' when a near-match exists.

### Remediation
Empty results should carry a `match_type` (exact/none) and an actionable next-step note (or a fuzzy/suggestion fallback), so the agent can distinguish a real miss from a malformed query and knows what to try next.

### Effort Estimate
S
