---
name: research-first
description: Enforce a research-then-propose-then-implement workflow whenever the task touches domain-specific decisions (pricing models, data formats, API conventions, regulatory requirements, industry workflows). Identifies assumptions, researches authoritative sources, presents a design brief, and waits for approval before coding. Skip for purely mechanical changes (rename, typo, log line).
---

# Research Before Implementation

When the user asks to implement a feature, enforce a research-then-propose-then-implement workflow. Never jump straight into coding when domain-specific decisions are involved.

## Step 1: Identify Domain Assumptions

Before anything else, analyze the request and list every business logic or design decision the implementation requires. These are the assumptions that, if wrong, cause costly rework.

Examples: pricing models, data formats, API conventions, industry workflows, standard terminology, regulatory requirements.

## Step 2: Research Each Assumption

For each identified assumption, research authoritative sources to determine the industry standard or best practice.

- Use web search and browser tools to find 3+ credible sources per key decision
- Prioritize: industry association guidelines, established platform documentation, domain expert publications, competitor implementations
- Note when there is genuine disagreement or multiple valid approaches

## Step 3: Present a Design Brief

Before writing ANY implementation code, present findings as a structured design brief:

### Design Decisions

| Decision | Options | Industry Standard | Sources | Recommendation |
|----------|---------|-------------------|---------|----------------|

For each row, clearly state what the options are, what most of the industry does, and what you recommend with reasoning.

### Identified Risks & Pitfalls

List common mistakes or anti-patterns discovered during research that the implementation should avoid.

### Proposed Approach

A concise summary of the recommended implementation approach based on the research.

## Step 4: Wait for Approval

**Do NOT proceed to implementation until the user explicitly approves the approach or requests changes.** Present the design brief and ask:

> Here's what I found. Does this approach look right, or should I adjust anything before implementing?

## Step 5: Implement with Traceability

Once approved:

- Follow the approved approach exactly — do not deviate without flagging it
- Where a design decision materially affects the code, add a brief comment noting the rationale (e.g., `# Using all-in pricing per industry standard — see design brief`)
- If during implementation you discover the approved approach won't work, stop and present the issue rather than silently switching approaches

## Notes

- This workflow applies whenever the task involves domain-specific logic, external API integration patterns, or business rules where conventions exist
- For purely mechanical tasks (rename a variable, fix a typo, add a log line), skip this workflow and just do the work
- If the user provides their own research or explicitly states the approach to take, skip to Step 5
