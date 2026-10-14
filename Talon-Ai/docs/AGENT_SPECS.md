# TALON AI - Agent specification cards

Two modes: LITE (default) runs ORIGIN, ATHENA, NORTHSTAR, OMNIVIEW. FULL runs all ten agents (Settings > Agents: full, then restart).

## Execution contract

Agentic execution is the default and requires a connected model. Every active stage uses the
model-driven action/observation/final loop, with up to six tool calls and a final response.
Model failures and invalid output stop the stage; they do not create approvals or advance it.
The Settings execution selector explicitly restores the legacy behavior described below.

- ORIGIN must search the resume; inferred skills require exact resume quotes and earn half credit.
- ATHENA retrieves courses and returns `ordered_skills` plus `summary`. All required gaps must
  appear once; up to two optional gaps are permitted. Catalog records supply course names and hours.
- APEX retrieves the curated question bank and returns `question_ids` plus `summary`.
  IDs must be distinct, cover every available bank skill and contain at most ten questions.
- GENESIS, NOVA, SENTINEL and PRISM must retrieve `get_stage_evidence`, then return `summary`
  and boolean `review_required`. AI can add review, never remove a mandatory review.
- TITAN, NORTHSTAR and OMNIVIEW interpret factual measurements and policy using tools.
  NORTHSTAR must retrieve policy. Objective scores, readiness thresholds and HOLDs remain enforced.
- SUPERVISOR uses its own evidence tool loop and may only add an allowed human reviewer.
- Ask TALON uses data tools and a validated `answer`; errors are returned explicitly.

All candidate agents can retrieve candidate context, resume passages, job requirements,
policy/framework documents and learning resources. Human approvals cannot be auto-approved
in Agentic mode. Routing remains fixed rather than model-selected.

The cards below describe deterministic safeguards and **legacy-mode** behavior. Statements
such as "pure rules" or "LLM only writes guidance" do not describe Agentic execution.

## SUPERVISOR + WORKFLOW RUNNER
Files: talon/supervisor.py, talon/workflow.py, talon/orchestrator.py

Goal: Decide what happens next for each candidate and enforce the human STOP gates.

Logic: Reads the candidate's stage and the approvals table. Routes to: run the next agent, STOP at a human approval gate, STOP for a candidate input form, or end. After each agent result the supervisor checks for borderline or weakly evidenced results (rules, plus an AI opinion if a model is connected) and can ADD an extra human reviewer. Smart routing: if ATHENA finds no skill gaps, LEARNING and NOVA are skipped. A rejection ends the journey (REJECTED). Every step is written to the audit log (ATLAS).

Guardrail: The supervisor can only make the process stricter (add a reviewer); it can never skip or remove an approval. Routing is deterministic code, so the workflow is predictable and auditable.

## 1. ORIGIN - Talent Discovery Agent
File: talon/agents/origin.py

- **Goal:** Find and rank the best-fit candidates, fast.
- **Reads:** Candidate resume (database), job required / nice-to-have skills.
- **Tools the LLM may call:** search_resume (RAG over THIS candidate's resume), get_job_requirements.
- **Rule-based logic (code):** Keyword + synonym skill extraction (talon/skills.py). Score = 70 x required-skill coverage + 20 x nice-to-have coverage + up to 10 points for years of experience. Rank among all candidates of the same job.
- **LLM task prompt:** Job: {title}. Skills matched by keywords: {matched}. Missing required skills: {missing}. For each missing skill, call search_resume to check if the resume shows real evidence. Finish with {"inferred_skills": [skills with evidence], "summary": "2 factual sentences"}.
- **Guardrails:** inferred_skills must be a subset of the missing skills (invented skills are dropped); AI-inferred skills earn only HALF credit; the score itself is computed by code; summary must be 5-600 characters.
- **Memory written:** ORIGIN: score, skills, result, trace.
- **Human approval gate:** Recruiter - ALWAYS (validates the shortlist before outreach).
- **Output:** Match score, rank, matched / missing / AI-inferred skills, 2-sentence summary.

## 2. GENESIS - Onboarding Agent
File: talon/agents/genesis.py

- **Goal:** Onboard verified candidates smoothly.
- **Reads:** Name, email, resume text, other candidates (duplicate check).
- **Tools the LLM may call:** None (pure rules - no LLM needed).
- **Rule-based logic (code):** Checks: name present, email format, resume at least 200 characters, no duplicate email. Identity validation is SIMULATED (no real ID check).
- **LLM task prompt:** (no LLM prompt)
- **Guardrails:** Deterministic only.
- **Memory written:** GENESIS: verification_status, profile, result.
- **Human approval gate:** HR - ONLY if any check fails.
- **Output:** verified / needs_review + list of issues.

## 3. ATHENA - Learning Intelligence Agent
File: talon/agents/athena.py

- **Goal:** Close each person's skill gaps with a personal plan.
- **Reads:** Job skills, ORIGIN skills, knowledge base (learning catalog + your documents).
- **Tools the LLM may call:** search_knowledge, search_resume, get_job_requirements.
- **Rule-based logic (code):** Gap = job skill not found in resume. Order: foundation skills first (excel, sql, python, statistics ...), required before nice-to-have. Each course is RETRIEVED by RAG from the learning catalog and the knowledge folder (lines like 'Learning resource for X: Title. Estimated N hours.'); falls back to the built-in catalog.
- **LLM task prompt:** Candidate for {title} has this learning plan: {plan}. Use search_knowledge (source docs) to check the learning guidance, then finish with {"summary": "2 encouraging, practical sentences"}.
- **Guardrails:** Plan is built by code from retrieved data; the LLM only writes the guidance text.
- **Memory written:** ATHENA: skill_gaps, plan, result, trace.
- **Human approval gate:** Learning Team - ALWAYS (approves the learning plan).
- **Output:** Learning plan (skill, course, hours, source), total hours, guidance text.

## 5. NOVA - Learning Progress Agent
File: talon/agents/nova.py

- **Goal:** Keep learners engaged and completing.
- **Reads:** ATHENA plan + the progress the candidate entered.
- **Tools the LLM may call:** None (pure rules).
- **Rule-based logic (code):** Completion = average progress over planned courses. Engagement: high >= 80, medium >= 50, else low. At risk if completion < 60.
- **LLM task prompt:** (no LLM prompt)
- **Guardrails:** Deterministic only. Skipped automatically when there is no learning plan.
- **Memory written:** NOVA: progress, completion_records, result.
- **Human approval gate:** Manager - ONLY if at risk (< 60%).
- **Output:** Completion %, hours done, engagement, at-risk flag.

## 6. APEX - Assessment Agent
File: talon/agents/apex.py

- **Goal:** Test the right competencies fairly.
- **Reads:** Job required skills, question bank (talon/skills.py).
- **Tools the LLM may call:** None (pure rules).
- **Rule-based logic (code):** Up to 2 multiple-choice questions per required skill (max 10), generic logic questions if no bank entry; adds a Python coding task if python is required. Maps skills to the competency framework.
- **LLM task prompt:** (no LLM prompt - questions come from the curated bank so answers are trustworthy)
- **Guardrails:** Curated question bank; no AI-written answer keys.
- **Memory written:** APEX: assessment, competencies_covered, result (later: submission).
- **Human approval gate:** Assessment Owner - ALWAYS (approves before assignment).
- **Output:** Assessment (questions + coding task) and the competencies covered.

## 8. SENTINEL - Integrity Agent
File: talon/agents/sentinel.py

- **Goal:** Keep assessments honest and compliant.
- **Reads:** The candidate's submission (answers, time, code, declaration), other candidates' code.
- **Tools the LLM may call:** None (pure rules).
- **Rule-based logic (code):** Flags: average time per question below 4 s; the same option chosen for every question; declared external help; code identical to another candidate's.
- **LLM task prompt:** (no LLM prompt)
- **Guardrails:** Deterministic and explainable - flags are shown to HR, never auto-punished.
- **Memory written:** SENTINEL: compliance_log, result.
- **Human approval gate:** HR - ONLY if violations found.
- **Output:** List of violations (or none), average seconds per question.

## 9. TITAN - Evaluation Agent
File: talon/agents/titan.py

- **Goal:** Score objectively and consistently.
- **Reads:** Assessment, submission, knowledge base (competency framework).
- **Tools the LLM may call:** search_knowledge, search_resume, get_job_requirements.
- **Rule-based logic (code):** Objective score = % correct. Coding score = candidate code run against 4 test cases in a separate Python process with a 5 s limit. Total = 70% objective + 30% coding (or 100% objective).
- **LLM task prompt:** Review this assessment result neutrally. Per-skill scores: {scores}. Coding: {coding}. Overall: {total}. Use search_knowledge (source docs) for the proficiency levels. Finish with {"summary": "2 neutral sentences, no hiring advice"}.
- **Guardrails:** Scores come from code only; the LLM writes the review text and may not give hiring advice.
- **Memory written:** TITAN: scores, evaluation_result, result, trace.
- **Human approval gate:** Interviewer - ALWAYS (reviews / can override AI scores).
- **Output:** Objective, coding and total score, per-skill scores, review text.

## 10. PRISM - Readiness Intelligence Agent
File: talon/agents/prism.py

- **Goal:** Show who is work-ready, and where.
- **Reads:** ORIGIN score, NOVA completion, TITAN scores, SENTINEL log.
- **Tools the LLM may call:** None (pure rules).
- **Rule-based logic (code):** Readiness = 30% match score + 20% learning completion + 50% assessment - 15 if integrity violations. Ready >= 75, Conditionally ready >= 55, else Not ready. Competency map = average per competency category.
- **LLM task prompt:** (no LLM prompt)
- **Guardrails:** Transparent formula; weights editable in the file.
- **Memory written:** PRISM: readiness, competency_mapping, result.
- **Human approval gate:** Hiring Manager - ALWAYS (validates readiness mapping).
- **Output:** Readiness score and level, strengths, weak skills, competency map.

## 11. NORTHSTAR - Recommendation Agent
File: talon/agents/northstar.py

- **Goal:** Turn evidence into hire, deploy or upskill calls.
- **Reads:** PRISM, TITAN, SENTINEL, knowledge base (hiring policy).
- **Tools the LLM may call:** search_knowledge, search_resume, get_job_requirements.
- **Rule-based logic (code):** Ready -> hire; Conditionally ready -> hire with upskilling plan; Not ready -> do not proceed. In LITE mode (4 agents) readiness = 60% match score + 40% learning ease (100 minus 2 points per planned hour); in FULL mode it comes from PRISM. POLICY RULES ARE ENFORCED IN CODE: integrity flags (full mode) or an unstated years-of-experience (rule 6) turn the recommendation into HOLD. Deployment = strongest competency area. Upskilling = skills under 70%. Policy passages are retrieved by RAG and attached as evidence.
- **LLM task prompt:** Explain to an HR approver this recommendation: {hire}. Readiness {readiness}. Integrity flags: {flags}. Call search_knowledge (source docs) to find the relevant policy, then finish with {"summary": "2 neutral sentences citing the policy; remind that a human decides"}.
- **Guardrails:** Policy as code (HOLD rule); final decision is always a human's.
- **Memory written:** NORTHSTAR: recommendation, result, trace. After approval: ORCHESTRATOR.decision.
- **Human approval gate:** HR - ALWAYS (final approval).
- **Output:** Hiring / deployment / upskilling recommendation + policy evidence.

## 12. OMNIVIEW - Executive Intelligence Agent
File: talon/agents/omniview.py

- **Goal:** Give leaders one trusted view of talent.
- **Reads:** All agents' memory for the candidate.
- **Tools the LLM may call:** search_knowledge, search_resume, get_job_requirements.
- **Rule-based logic (code):** Assembles the candidate report; portfolio() computes dashboard numbers (funnel, pending approvals, average readiness).
- **LLM task prompt:** Write an executive summary of this candidate report: {report}. Finish with {"summary": "3 short factual sentences"}.
- **Guardrails:** The report data comes from memory; the LLM only summarises it.
- **Memory written:** OMNIVIEW: executive_report, result, trace.
- **Human approval gate:** Executive - ALWAYS (sign-off).
- **Output:** Executive report + summary (documentation + summarisation).
