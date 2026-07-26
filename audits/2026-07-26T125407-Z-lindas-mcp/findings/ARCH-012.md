## Finding: ARCH-012 — protocolVersion-Pinning + CHANGELOG + SDK-Update-Disziplin

**Severity:** medium
**Status:** open
**Server:** lindas-mcp
**Check-Reference:** ARCH-012 (partial)
**PDF-Reference:** Anhang A9

### Observed Behavior
`FastMCP("lindas-mcp")` is created with no `protocol_version` argument (SDK default is used); the README has no MCP-protocol-version / breaking-change policy section. CHANGELOG + Dependabot are present.

### Expected Behavior
Pin the negotiated MCP `protocolVersion` (or document the SDK-managed range) and add a short 'MCP Protocol Version' / breaking-change policy to the README so SDK upgrades are a reviewed decision.

### Evidence
- server.py:47 — mcp = FastMCP('lindas-mcp'); no protocol_version argument; grep for protocol_version|protocolVersion returns NONE
- CHANGELOG.md present in Keep-a-Changelog + SemVer format
- .github/dependabot.yml — pip ecosystem monthly ('keep protocol support current')

### Gaps
- protocolVersion not pinned in server code (takes SDK default)
- CHANGELOG entries do not reference any MCP spec/protocol-version bump
- README has no 'MCP Protocol Version' section and no spec-update/breaking-change policy

### Risk Description
An SDK upgrade can silently change the negotiated protocol version and break clients without a reviewed decision.

### Remediation
Pin the negotiated MCP `protocolVersion` (or document the SDK-managed range) and add a short 'MCP Protocol Version' / breaking-change policy to the README so SDK upgrades are a reviewed decision.

### Effort Estimate
S
