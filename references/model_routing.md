Model-routing note adapted to this VPS install:

The original draft used codex-mini-latest for cheap roles.
That model name is not present in this Hermes install's Codex support logic.

Safer v1 routing:
- provider: openai-codex
- writer: gpt-5.4
- writer fallback: gpt-5.3-codex
- research/review/synthesizer/quality gate: gpt-5.3-codex

Reason:
- current config is already openai-codex
- gpt-5.3-codex is the safest native Codex slug in this install
- gpt-5.4 is accepted and already configured as the user's default, so it is used for the strongest long-form role
