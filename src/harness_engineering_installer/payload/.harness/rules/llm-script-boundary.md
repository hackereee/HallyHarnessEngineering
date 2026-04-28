# LLM And Script Boundary

This rule defines the Harness Engineering boundary between deterministic scripts and LLM semantic judgment. It is a fixed `.harness/` rule asset so installed skills never depend on source-only learning material.

## Principle

Do not replace deterministic gates with LLM judgment.

- Scripts handle operations that must be deterministic, auditable, repeatable, and cheaply testable.
- LLMs handle semantic judgment, planning prose, handoff summaries, closure analysis, and exception reasoning.

## Script Responsibilities

Scripts own constraints that can be expressed with schema, parsing, finite rules, or atomic file operations:

- JSON Schema validation and enum constraints.
- Cross-file consistency checks.
- Atomic writes and path moves.
- Manifest, template, and required asset checks.
- Task materialization from reviewed, structured task contracts.
- State writes through approved gateways such as `state-write.py` and `update-task.py`.

Scripts must not infer business intent, invent task semantics, decide whether prose is sufficient, or silently repair workflow conflicts from natural language.

## LLM Responsibilities

LLMs own semantic work that cannot be reliably represented as a fixed deterministic rule:

- Classifying task level when the input is ambiguous.
- Writing and reviewing plan, handoff, and closure prose.
- Deciding whether `nextAction` is truly atomic.
- Assessing whether acceptance, verification, and review evidence are meaningful.
- Explaining conflicts and recommending fixes when deterministic checks fail.

LLM output must still be written through the relevant script gateway when it changes runtime state.

## Double-Signed Actions

High-impact actions require both script evidence and LLM review:

- Archive or complete workflow: script performs the deterministic move/state transition; LLM checks closure quality and unresolved risks.
- Task selection: script produces the legal candidate set; LLM may choose among valid candidates when semantic priority matters.
- State transition: script validates schema and cross-file invariants; LLM verifies the transition reflects the real work completed.

## Hard Boundary

If a constraint can be encoded in schema, parser logic, or a deterministic script, encode it there. Rules documents explain semantics that schemas cannot express; they do not replace machine checks.
