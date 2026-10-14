# TALON AI

**Agentic Gen AI for talent: from resume to workforce readiness.**
Four specialised agents, grounded in company knowledge (RAG), with a named human approving every decision.

> Hackathon 2026 prototype. Built with open-source code and **synthetic data only**.

---

## The problem

Talent decisions are slow, inconsistent and hard to explain. Resumes, assessments and learning data sit in separate systems, teams rewrite summaries by hand, and a plain chat AI does not help: it does not know company policy, it can invent facts, and it cannot run a process with approvals.

**TALON** turns unstructured resumes and company knowledge into trusted, explainable, human-approved talent decisions.

## What it does

An orchestrator runs four agents in order and **stops for a named person at every decision**:

| Agent | Job | Human approval |
|---|---|---|
| **Origin** | Reads the resume against the job: skill match, ranking, fit summary | Recruiter |
| **Athena** | Builds a foundations-first learning plan from the learning catalog and writes guidance | Learning Team |
| **Northstar** | Hire / deploy / upskill recommendation, grounded in the hiring policy; enforces HOLD rules in code | HR (final approval) |
| **Omniview** | Executive summary and documentation of the journey | Executive |

A **supervisor** decides what happens next and can *add* an extra human reviewer on borderline results. It can never skip an approval.

### Agentic Gen AI features

1. **Multi-agent orchestration** with a supervisor and human STOP gates
2. **RAG with visible sources**: evidence from policy documents, the competency framework and each resume
3. **Guardrails and policy as code**: unsupported AI claims are dropped; for example, a candidate with no stated experience is put on HOLD
4. **Content creation**: summaries, learning plans, candidate dossier (printable), draft emails, interview guide
5. **Ask TALON**: leaders ask questions in plain English over live data

### Screens

Command Center (KPIs, live agent activity, business impact, Gen AI usage and spend), Talent Pipeline board, Approvals inbox by role, candidate case file (agents, evidence, audit trail), Knowledge Base search, Agent Workflow map, Settings.

<!-- Add screenshots here after uploading them to the repo, for example:
![Command Center](docs/command-center.png)
-->

## Quick start (5 minutes)

**You need:** Python 3.10 or newer and a browser. No packages to install.

1. Download this repository (Code > Download ZIP) or clone it, and open the folder that contains `run.py`.
2. Run:

   ```bash
   # Windows
   py run.py

   # Mac / Linux
   python3 run.py
   ```

3. Open **http://localhost:8000** (it opens automatically) and click **Load demo portfolio**.

Optional: `pip install pypdf` to read PDF resumes (TXT and pasted text work without it).
Self-test: `py run_tests.py` (last line should read `ALL CHECKS PASSED`).

### Modes

- **Lite (default):** the 4 agents above.
- **Full:** 10 agents (adds onboarding, progress, assessment, integrity, scoring, readiness). Settings > Agents, then restart.

## Connecting an AI model (optional)

Without a model the app runs in **Rules mode**: scores, retrieval, policy rules, workflow and approvals all work, and text comes from templates. With a model, agents read evidence and write summaries.

Settings > AI engine supports:

- **Custom API** (for example an organisation's Generative Engine platform): URL, auth header, request body template and response path are configurable. A **copy/paste bridge** is also available if no API key exists.
- **GitHub Models** (fine-grained token with the *Models: Read* permission)
- **Ollama** (local models)
- **Any OpenAI-compatible API**

**Credit protection:** choose which agents may call the model, set a maximum number of AI calls, and enter your price per 1,000 tokens; the Command Center shows estimated spend against your credit.

Agent definitions to create on a hosted platform are in [`docs/PLATFORM_AGENTS.md`](docs/PLATFORM_AGENTS.md). Full agent specifications are in [`docs/AGENT_SPECS.md`](docs/AGENT_SPECS.md).

### API keys: never commit them

Keys entered in Settings are saved to `data/settings.json` on your own computer. You can also use environment variables (`TALON_CUSTOM_KEY`, `TALON_GITHUB_TOKEN`). **Do not upload the `data/` folder.** The included `.gitignore` excludes it.

## How it works

```
Resume + job  ->  Origin  -> STOP (Recruiter)
              ->  Athena  -> STOP (Learning Team)
              ->  Northstar -> STOP (HR)  <- hiring policy retrieved with RAG
              ->  Omniview -> STOP (Executive)

Supervisor: routes each case, can add a reviewer, never removes one
Knowledge base: policy | competency framework | learning catalog | resumes
```

1. Rules compute the facts (skills, scores, gaps).
2. The Gen AI agent receives the task plus retrieved evidence and answers in JSON.
3. Code **validates** the answer (for example, skills not on the missing list are dropped). Invalid output or no model falls back to the rule-based result.
4. The agent asks for a human approval and the workflow stops.

Add your own knowledge by placing `.txt` or `.md` files in `knowledge/` and clicking **Re-index** on the Knowledge Base page.

## Project structure

```
run.py                  start the web app
run_tests.py            self-test (lite and full modes)
web/                    the interface (HTML, CSS, JavaScript; works offline)
talon/                  server, workflow, supervisor, agents, RAG, AI connectors
talon/agents/           the agents
knowledge/              policy and guidance documents used for RAG
sample_data/            one job and six synthetic resumes
docs/                   agent specifications and platform agent definitions
data/                   created at run time (database, settings) - not committed
```

## Responsible AI

- **People decide.** The AI prepares and explains; a named person approves each step.
- Scores are computed from skills and experience, not from name, gender, age or photo.
- Every recommendation cites its evidence and policy; every approval is logged (who, when, why).
- We do **not** claim the system is bias-free. It is designed to reduce and expose bias. Formal fairness testing (for example name-swap tests and outcome comparison) is planned for a pilot.
- Prototype only: synthetic data, no login, simulated identity checks, heuristic integrity checks.

## Cost analysis (illustrative)

Assuming $30 per hour and 105 minutes of manual effort per candidate, manual handling is about $52.50. With TALON, human review takes about 8 minutes (about $4.00) and the AI adds about $0.01. These are assumptions to be replaced with measured values in a pilot.

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` not recognized (Windows) | Use `py run.py`, or reinstall Python with "Add python.exe to PATH" |
| Browser does not open | Go to http://localhost:8000 (the terminal shows the port) |
| AI test fails | Settings shows the exact message; switch to Rules mode to continue |
| Changed lite/full mode | Restart the app |
| Start clean | Settings > Reset all data |

## Status

Hackathon prototype. Tested with a scripted stand-in AI service in both modes; not yet tested against every external AI platform. Use synthetic data only.
