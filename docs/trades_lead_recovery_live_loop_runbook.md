# Trades Lead Recovery — Live Loop Runbook
**Version:** 5.0  
**Organ:** Trades Lead Recovery  
**Architecture:** RHNS + Agent Registry + Revenue Plane  
**Status:** Operational Runbook  

## Purpose
Execute a full-stack, governed lead-to-cash loop for DFW trades leads (roofing, HVAC, plumbing, etc.) using the RHNS Recursive Goal Tree, registered agents, and approval gates. Every cycle produces attributable revenue events and compounds knowledge.

## Prerequisites
- Agent registry loaded (`docs/schemas/agent_registry.schema.json`)
- Goal tree active (`docs/schemas/trades_lead_recovery_goal_tree.json`)
- Dual-tier state available (hot Redis + cold graph)
- Docker sandboxes running per `infra/docker-compose.revenue-loop.yml`
- StandardsGate / approval workflow enabled for outreach
- Stripe livemode keys present and validated (GAR-399 style check)
- Opt-out and mailing-address compliance lines configured

## Startup Sequence
1. Start control plane and state stores:
   ```bash
   docker compose -f infra/docker-compose.revenue-loop.yml up -d
   ```
2. Confirm registry and goal tree are mounted.
3. Verify agent sandboxes are healthy (`signal-ingest-v2`, `trades-qual-v3`, `outreach-draft-v1`, `stripe-fulfill-v2`, `attrib-learn-v1`).
4. Emit readiness event to Metacognitive Controller.

## Live Loop Flow (Signal → Cash)
1. **Signal Ingestion** (`signal-ingest-v2`)
   - Ingest lead from form, TREC-adjacent source, or webhook.
   - Perceptual Fusion Layer normalizes into symbolic representation.
   - Write to hot state. Hand off to qualify node.

2. **Qualification & Scoring** (`trades-qual-v3`)
   - Score opportunity.
   - Constraint check: `score >= 0.7`.
   - If fail → log and close cycle (no outreach).
   - If pass → hand off with score and reasons.

3. **Approval-Gated Outreach** (`outreach-draft-v1`)
   - Generate draft with opt-out line and mailing address.
   - StandardsGate hold: human or policy approval required before send.
   - No weekend sends. DFW-only. No $47 language.
   - On approval → send and record message_id.

4. **Payment & Entitlement** (`stripe-fulfill-v2`)
   - On checkout or invoice paid (`paid=true`, not test card).
   - Capture charge, grant entitlement, trigger fulfillment.
   - Write payment event to dual-tier state.

5. **Attribution & Learning** (`attrib-learn-v1`)
   - Record outcome, margin, cycle trace.
   - Enrich Federated Knowledge Graph.
   - Propose new skill schemas via NSP if pattern repeats.
   - Close loop and emit observability event.

## Governance Gates
- Symbolic Constraint Engine evaluates every handoff.
- Metacognitive Controller audits path before external action.
- Outreach and payment require explicit pass from StandardsGate.
- High-risk patterns (refund, force push, raw secret) auto-hold.

## Monitoring & Observability
- Hot state: current cycle status.
- Cold graph: historical patterns and skill growth.
- Proof certificates emitted for payment and attribution nodes.
- Failed constraints or timeouts escalate inside the tree before human alert.

## Failure Handling
- Retry leaf once under CMC.
- On persistent failure: mark node failed, notify parent, preserve state for resume.
- Stripe insufficient-funds or 4242 test-card events pause payment node and alert.
- Opt-out received → immediately suppress future outreach for that lead.

## Revenue Attribution
Every successful cycle writes:
- Lead ID
- Offer selected
- Stripe charge ID (paid=true)
- Margin
- Time-to-cash
Back to the Federated Knowledge Graph so subsequent cycles improve scoring and offer selection.

## Operator Checklist (per cycle)
- [ ] Signal normalized
- [ ] Score ≥ 0.7
- [ ] Outreach approved
- [ ] Payment confirmed paid=true
- [ ] Attribution written
- [ ] Graph enriched

## Next Improvements
- Auto-skill synthesis from successful traces
- Multi-vertical organ handoff (real-estate speed-to-lead)
- Metered quote line tied to existing live SKUs

---
*This runbook operationalizes the v5.0 Full Build-Out for live revenue generation. All agents, schemas, and compose definitions are in the same repository.*
