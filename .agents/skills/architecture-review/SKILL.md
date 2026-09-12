---
name: architecture-review
description: Post-implementation review skill that evaluates a git diff or completed feature against architectural baselines. Reports concrete complexity/duplication deltas, newly introduced problems, and reuse opportunities.
---

# Architecture Review — Post-Implementation Audit

Use this skill after implementing a feature, bugfix, or pull request to verify that the changes did not introduce structural regressions, duplicate logic, or accidental complexity.

---

## When to Run

- Immediately before finalizing a feature or opening a PR.
- When reviewing a completed branch or staged set of changes.
- To audit the structural impact of a diff on the system.

---

## Review Checklist

When evaluating the changes, answer these 7 specific questions with data:

1. **Did this change unnecessarily increase architectural complexity?**
   - Did average or maximum CCN spike without clear justification?
2. **Did it duplicate existing functionality?**
   - Did jscpd detect new clone groups in modified files?
3. **Did it introduce new dependency relationships?**
   - Did Valknut flag new import cycles or tight coupling?
4. **Is complexity growth proportionate to functionality?**
   - Did a simple 10-line feature introduce 150 lines of boilerplate or helper wrappers?
5. **Did it create new hotspots?**
   - Are any newly added or modified functions listed with CCN > 15?
6. **Did it resolve or worsen existing hotspots?**
   - Did the diff improve existing technical debt or compound it?
7. **Are there overlooked reuse opportunities?**
   - Did the author write a custom utility when an existing one was already present?

---

## Step-by-Step Review Execution

### 1. Run Diff-Aware Architecture Comparison
```json
call_mcp_tool(
  ServerName="architecture_fitness",
  ToolName="architecture_compare",
  Arguments={
    "repo_path": "/path/to/repo",
    "baseline_name": "HEAD",
    "diff_aware": true
  }
)
```

### 2. Search Reuse Candidates for New Functions
If the diff added new functions or classes, run:
```json
call_mcp_tool(
  ServerName="architecture_fitness",
  ToolName="architecture_reuse_candidates",
  Arguments={
    "repo_path": "/path/to/repo",
    "query": "<name or description of new function>"
  }
)
```

### 3. Synthesize the Audit Report
Present your review using concrete metrics from the tool output:

```markdown
### Architecture Review Findings

| Dimension | Baseline | Current | Delta | Status |
|---|---|---|---|---|
| Duplication Rate | X.X% | Y.Y% | +Z.Z% | NEUTRAL / REGRESSION |
| Max Complexity (CCN) | A | B | +C | NEUTRAL / REGRESSION |
| Functions Count | N | M | +K | NEUTRAL |
| Clone Groups | P | Q | +R | NEUTRAL / REGRESSION |

#### Newly Introduced Problems
- [List exact files, line numbers, and function names]

#### Reusability Opportunities
- [List existing symbols identified by architecture_reuse_candidates]

#### Verdict & Recommendations
- [Clear accept or revise recommendation based on objective vector]
```
