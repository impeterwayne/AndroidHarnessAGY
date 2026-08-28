# Roster evals — step 9

Measures whether the pieces built in steps 4–8 actually help, by running the same
task twice: once with the harness feature active (`with_skill`), once without
(`without_skill`). Shape lifted from
`oh-my-openagent/.agents/skills/work-with-pr-workspace/`, pinned `b98042a30`.

Until this runs, the roster is untested in the only way that matters. Every prior
step proved its piece *works*; none proved a piece *helps*.

## Layout

```
evals.json                      the 5 tasks, their treatments, their assertions
iteration-1/
  eval-N/
    eval_metadata.json          frozen copy of the task as run
    with_skill/
      outputs/                  whatever the run produced (plan, diff, report)
      grading.json              one entry per assertion: passed + evidence
      timing.json               duration_ms, total_duration_seconds
    without_skill/              same, control arm
  benchmark.json                aggregate — written after all 10 runs
  benchmark.md                  the human-readable version
```

Deviation from upstream: OMO nests the harness inside the skill under test. Ours
sits at `.agents/evals/` because the subject is the roster, not one skill.

## Running an arm

**It must be an interactive `agy` session in this workspace.** Two recorded findings
forbid the scriptable route:

- `--agent <name>` is ignored in `--print` mode — `agy --agent does-not-exist -p …`
  returns clean, so print mode cannot exercise custom agents at all.
- In sandboxed non-interactive runs, workspace agents are not discovered
  (`agy agent` empty; `invoke_subagent` sees only `self` and `research`) because the
  CLI falls back on GeminiDir resolution and reports not being logged in.

If either is ever fixed, `--print --output-format stream-json` becomes the runner and
this file should say so.

1. **One fresh conversation per arm.** The hooks key state on `conversationId`
   (`intent_gate` byte offsets, `write_guard` verdicts, `loop.py` state dirs), so a
   reused session contaminates the next arm.
2. **Set up the control arm** per that eval's `without_skill_setup`. Hook arms use the
   escape hatches rather than config edits — `python .agents/hooks/<hook>.py --off` for
   `intent_gate`, `write_guard`, `stop_verifier`; `kotlin-rule-gate` has no `--off`, so
   flip `"enabled": false` in `hooks.json` and flip it back.
3. **Reset the corpus between runs.** `CodebaseCompose` is a real checkout —
   `git -C D:\Quest\CodebaseCompose checkout . && git -C D:\Quest\CodebaseCompose clean -fd`
   before each arm, or the second arm grades a tree the first one already fixed.
4. **Capture outputs** into `outputs/` — the plan, the final diff (`git diff > diff.patch`),
   and the session's closing report. These are the evidence `grading.json` cites.
5. **Timing** comes from the transcript: last `created_at` minus first, in
   `%USERPROFILE%\.gemini\antigravity-cli\brain\<conversationId>\.system_generated\logs\transcript_full.jsonl`
   (`brain`, singular — and the `.system_generated` segment is easy to miss).
   Record the `conversationId` in `grading.json` so the run stays traceable.

## Grading

Assertions are `type: manual` — a human reads `outputs/` and fills `passed` plus a
one-line `evidence` quote, same as upstream. Do not grade from memory of the session;
grade from the artifacts, or the arm is worthless as a record.

Two assertion classes need the transcript rather than the diff:
`delegated-not-self`, `explore-dispatched`, `parallel-fanout`, `explored-the-pattern`,
`scope-held` and `gate-fired-once` are all claims about *tool calls*, so check them against
`transcript_full.jsonl`, not the report the agent wrote about itself.

## Reading the result

Upstream's own lesson, worth applying before iteration-2 rather than after:
assertions that pass in both arms measure baseline model competence, not the
harness. Sort them out in `benchmark.md` under "Non-discriminating assertions"
and drop them next iteration.

A null result is a real result here. If `executor` grades the same as the plain
session, that is the evidence for deleting it — and `agy.exe` ships `DeepCoder` and
`DeepInvestigator`, hidden but invocable, which `executor` may simply be
reinventing.

Note what evals 1 and 2 now measure. They used to test *tier selection* — a routing
decision that no longer exists, since `worker-quick` and `worker-deep` were merged into
`executor` (`model:` accepts only `inherit`, so the two tiers ran the same model and the
choice bought nothing). The replacement assertions, `explored-the-pattern` and
`scope-held`, test whether `executor` sizes its own exploration from the goal: reading the
pokedex pattern before a multi-file build, and touching only the two named files for a
mechanical one. That is the behaviour the merge is betting on, so it is the behaviour to
grade.
