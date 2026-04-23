# Kundur Intent vs Manifest Boundary

## Status
Accepted

## Context
Kundur SPS migration needs a durable external config layer and a durable
structure-fact layer. Repeated ad hoc MATLAB inspection is too expensive.

## Decision
- JSON profiles may configure only known semantic slots.
- JSON profiles may not declare arbitrary topology, wires, ports, or block paths.
- Semantic manifests are exported facts from Simulink and are read-only.
- Harness integrates manifests through existing tasks; no new task family is added.

## Consequences
- Config drift and structure drift become separately diagnosable.
- MCP/MATLAB inspection becomes baseline capture, not a repeated debugging loop.
