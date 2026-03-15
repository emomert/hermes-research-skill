Feedback handling schema:

1. Capture raw feedback text.
2. Detect stable preference updates:
   - depth
   - tone
   - sourcing / citation density
   - structure / readability
3. Append feedback record to the latest run.
4. Update global failure_tracker.json and editorial_heuristics.md.
5. If a failure type appears in 3 or more runs, generate a concrete prompt-update proposal in prompt_update_proposals.md.
6. The Hermes agent should also store durable user preferences with the memory tool when obvious.
