# Sovereign One — RHNS System (sovereign-1)

**Status:** Architecture + organ contract. Local proof preferred. Production writes host-keyed.

Sovereign One is the live executive stack over ZEUS (proof), Garcar (cash + fulfillment), and BioForge (organs). This folder is the RHNS binding for that stack.

## Purpose
Bind the BioForge Revenue organ and walking skeleton to the RHNS substrate (RGT, HRM, CMC, Federated KG, Audit Ledger) so every monetizing hop requires an explicit CMC `commit` and writes the audit ledger.

## Binding
- Planner: RGT + HRM H-module
- Gate: Metacognitive Controller (CMC)
- Memory: Federated Knowledge Graph
- Audit: append-only ledger (detach retains rows)
- Thresholds: commit ≥ 0.72 confidence and < 2 contradictions; escalate at 3 stalls; abort at 2 contradictions

## Revenue Spine Hops (governed)
1. Lead intake — revenue.intake
2. Enrichment — revenue.enrich
3. Outreach — outreach.send (**CMC commit**)
4. Proposal — proposal.generate
5. Checkout — billing.checkout (**CMC commit**)
6. CRM sync — crm.sync
7. Fulfillment trigger
8. Executive reporting

## Files
- `revenue_organ.yaml` — BioForge module contract for the Revenue organ
- `sovereign_one.py` — RHNS system entry point (extends substrate, does not replace core agent)
- Full design: `../../docs/sovereign-one-bioforge-full-design.md`

## Baseline proof (this session)
- proof_hash: `2398aa32e69202313aeccadacb6638f32eb7e9df5697ad93f080a4fcc05a3060`
- seal_id: `seal_dc0d2fab3bad9bac2c09cc0e`

## Rules
- No detach path → incomplete organ
- Money / reputation hops require CMC `commit`
- ZEUS remains the executive proof loop; this system is the RHNS substrate under BioForge organs
- Estimates are intelligence; cash is Stripe paid=true (last4 ≠ 4242)

Author: Garrett Carrol / Garcar Enterprise  
Added: 2026-11-26
