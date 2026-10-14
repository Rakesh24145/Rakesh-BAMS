# TALON Studio (platform edition)

Agentic AI + RAG talent intelligence with human approval gates. Python standard library only
(pypdf optional, for PDF resumes).

    py run.py            (Mac/Linux: python3 run.py)      then open http://localhost:8000

- Lite mode (default): 4 agents - Origin, Athena, Northstar, Omniview. Full mode: 10 agents (Settings).
- Execution defaults to **Agentic**: connect an AI engine in Settings before running agents.
  Existing provider settings and API keys are preserved. Supported engines: Capgemini
  Generative Engine / custom API, GitHub Models, Ollama, and OpenAI-compatible APIs.
- Every active agent, the review supervisor and Ask TALON use a bounded model-driven
  tool loop. Agents select evidence tools, observe results, and produce validated outputs.
  ATHENA chooses learning order and optional skills; APEX selects approved assessment questions.
- Missing providers, exhausted AI budgets, malformed outputs and failed model calls pause
  the stage with a visible error and Retry action. There is **no silent rules fallback**.
- Human approvals and candidate input remain mandatory. Demo auto-approval is disabled in
  Agentic mode, including when loading samples. Scores, answer keys, readiness thresholds
  and hiring-policy HOLDs remain deterministic safeguards; workflow stage routing is fixed.
- For the previous offline behavior, explicitly choose **Legacy** execution in Settings.
  Agent selection and single-call options apply only in Legacy; Agentic enables all active agents.
- Hosted/custom endpoints must follow the runtime's action/final JSON protocol across
  repeated requests. Fixed-summary platform agents are only compatible with Legacy mode.
- Copy-paste agent definitions for your platform: docs/PLATFORM_AGENTS.md
- Agent details: docs/AGENT_SPECS.md
- Self-test: py run_tests.py (legacy lite/full regressions plus scripted/local-HTTP agentic tests;
  no credentials or external network required).
- Put your own policy documents (.txt / .md) in the `knowledge` folder.
- Keys: Settings page (saved in data/settings.json) or env var TALON_CUSTOM_KEY. Never share the data folder.

## Start agentic execution

1. Run `py run.py`, open Settings, and keep Execution mode set to Agentic.
2. Select your provider, enter the model/endpoint and credentials, then Save and Test connection.
3. Use lite mode for the four-stage workflow, or select full and restart for all ten agents.
4. Add a candidate or load sample data. Review each pending approval yourself.
5. Inspect each candidate's agent trace to see tool requests, evidence and final outputs.

## Reliable presentation demo (no API calls)

To restart from the beginning in the current window, click **Reset portfolio** on the
Command Center (or **Reset portfolio (keep connections)** in Settings), confirm, then
click **Load demo portfolio**. Reset removes candidates, jobs, results, approvals and
portfolio activity only. It preserves existing provider connections, keys, execution
settings, knowledge documents and usage history. Wait for active agents or a sample load
to finish first; reset is refused while they are working. It does not delete the database
file or silently report success on an error.

Click **Open offline showcase** in the top bar, then **Open showcase window** when it is ready.
This opens the original rules-based
presentation flow in a separate window, with six synthetic candidates: completed journeys,
policy HOLDs and human approval queues. It is visibly labeled **OFFLINE SHOWCASE** and is
not a demonstration of model-driven reasoning.

The showcase runs in its own process with a temporary database and a copy of the knowledge
folder. It does not change the main application's execution mode, provider, keys, candidates
or knowledge files. No credentials are required and no model budget is consumed. Provider
settings are fixed in the showcase; configure live AI in the main window.

The separate server remains available while the main application is running; stopping the
main application stops the showcase and removes its temporary data. If your browser prevents
the new window, copy the local address shown in the ready dialog. Loading samples in Agentic mode now explicitly offers either
this offline showcase or **Load AI samples here**. The latter still pauses for real approvals
or invalid model output, and does not promise the old automatically completed portfolio.

A connection test verifies basic provider JSON responses, not end-to-end tool-protocol compliance.
For custom platform agents, remove fixed-summary-only instructions and allow the runtime's requested
JSON action/final envelopes. Each tool call adds a model round trip, so review the AI call budget
and token ledger. The call budget is cumulative across the stored ledger, not per candidate.

This remains a local prototype, not a production hiring or code-execution service. Identity
checks are simulated; the assessment code evaluator is not a secure sandbox.

## No API keys: local open-source model

Use **Ollama (local)** in Settings to run Qwen2.5 on your own computer:

1. Install Ollama from https://ollama.com/download/windows (or `winget install --id Ollama.Ollama --exact`).
2. In PowerShell, run `ollama pull qwen2.5:3b` to download the lightweight instruction model.
3. Start the Ollama application, or run `ollama serve` if its background server is not running.
4. In TALON Settings choose Ollama, URL `http://localhost:11434`, and model `qwen2.5:3b`.
5. Leave Embedding model blank to use built-in local retrieval without another model download.
6. Save and Test connection. Keep Execution mode Agentic.

No API key or cloud subscription is needed. Installation and model downloads require internet;
inference through the localhost endpoint stays local. The initial model download is roughly 2 GB.
On a 16 GB laptop without a dedicated GPU, CPU inference may take tens of seconds or longer per
model call. `qwen2.5:7b` is an optional larger model if the 3B model struggles with complex
instructions. Smaller models can still produce invalid outputs; the application pauses rather
than accepting them. A successful connection test is not a guarantee of every agent's accuracy.

Settings reports an explicit `ollama pull <model>` instruction when the selected model is absent.
The cumulative AI call budget still applies to local inference to bound work. Ledger estimates
represent cloud-equivalent token costs, not an Ollama API bill; electricity/hardware costs remain.

## OpenAI-compatible gateway errors

TALON sends non-streaming chat requests (`stream: false`) and does not send `stream_options`.
If an approved gateway returns HTTP 500 wrapping an upstream 400 about `stream_options`,
the gateway may be adding an unsupported parameter. Test connection shows up to 4,000
characters of the error, with configured API keys redacted. Share only a redacted error
with the platform support team; do not share credentials or request content.
Restart TALON after code updates before testing again.
