---
name: architecture-check
description: Use before and during feature implementation to inspect existing architecture, search reuse candidates, establish baselines, and prevent accidental complexity or duplication regressions.
---

# Architecture Check — Feature Implementation Conscience

Use this skill whenever you are about to plan or implement a new feature, add a new subsystem, create a new utility, or write non-trivial code.

Coding agents often fall into a trap: writing brand new functions, classes, wrappers, or helper modules from scratch rather than discovering and reusing mechanisms already in the codebase. This leads to code bloat, split mental models, duplicate logic, and architectural decay.

This skill equips you with an objective measurement loop to prevent that failure mode.

---

## The Core Guiding Principles

1. **Benefit of the doubt**:
   > *New mechanism requires justification; existing mechanism gets the benefit of the doubt.*

2. **Smallest necessary increase**:
   > *Prefer the implementation that satisfies the requirement with the smallest necessary increase in total system complexity.*

3. **Equivalence rule**:
   > *If two implementations satisfy the requirement equivalently, prefer the one that reuses existing mechanisms and produces the smaller measurable architectural footprint.*

4. **Necessary vs. Accidental Complexity**:
   - **Necessary complexity**: Writing 250 LOC with appropriate control flow to implement a genuinely novel capability (e.g. adding a new export format). This is healthy and expected.
   - **Accidental complexity**: Re-implementing an existing date-parser, introducing an abstract factory wrapper around a single function, copying an existing algorithm with minor tweaks, or creating circular import dependencies. This must be prevented.

5. **Avoid Simplistic Dogma**:
   - Do **NOT** say "always minimize lines of code" (golfing code into unreadable one-liners is bad).
   - Do **NOT** say "never add new abstractions" (good domain abstractions are vital).
   - Do **NOT** say "always reduce complexity" (new capabilities inherently add domain functionality).
   - **DO** investigate whether a regression in complexity or duplication is necessary before accepting it.

---

## Step-by-Step Workflow

### Step 1: Establish or Verify Baseline
Before modifying source files, ensure a baseline exists for the current worktree:
```json
call_mcp_tool(
  ServerName="architecture_fitness",
  ToolName="architecture_baseline",
  Arguments={"repo_path": "/path/to/repo", "name": "pre-feature"}
)
```
This freezes the pre-task complexity vector (LOC, cyclomatic complexity, duplication %, clone groups, Valknut health).

### Step 2: Search for Existing Mechanisms (Reuse First)
Before introducing a:
- new function or utility
- new class or data structure
- new configuration option
- duplicate algorithm or parser

Query the reuse candidate finder:
```json
call_mcp_tool(
  ServerName="architecture_fitness",
  ToolName="architecture_reuse_candidates",
  Arguments={
    "repo_path": "/path/to/repo",
    "query": "description of functionality or symbol name",
    "context": "parameter types or related domain concepts"
  }
)
```
- Inspect returned candidates in the codebase using `view_file`.
- Ask: *Can an existing function or class be reused, parameterized, or cleanly extended?*
- If an existing mechanism fits, reuse it!
- If a new mechanism is genuinely needed, proceed with implementation.

### Step 3: Implement Minimal Necessary Mechanism
- Implement the feature cleanly.
- Prefer extending existing well-tested modules over creating new standalone wrapper files unless separation of concerns genuinely warrants a new module.

### Step 4: Measure and Compare Against Baseline
Run architecture comparison:
```json
call_mcp_tool(
  ServerName="architecture_fitness",
  ToolName="architecture_compare",
  Arguments={
    "repo_path": "/path/to/repo",
    "baseline_name": "pre-feature",
    "diff_aware": true
  }
)
```

### Step 5: Evaluate the Delta
Read the summary header:
- `ARCHITECTURE RESULT: NEUTRAL` or `IMPROVED`: Excellent. Proceed to test verification.
- `ARCHITECTURE RESULT: REGRESSION`:
  - Check **New problems introduced in this change**:
    - *Did duplication increase?* Look at the exact files in the clone group. Extract common logic or call the existing function.
    - *Did maximum complexity spike (CCN > 15)?* Decompose deep conditionals or branch tables into smaller cohesive functions.
    - *Did Valknut detect circular dependencies?* Break the cycle before committing.
  - If the regression is *accidental complexity*, revise your implementation and measure again.
  - If the increase is strictly *necessary complexity* for novel functionality, document why and proceed.
