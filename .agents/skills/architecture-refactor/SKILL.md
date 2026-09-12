---
name: architecture-refactor
description: Use for deliberate architecture improvement and technical debt reduction. Identifies objective hotspots, guides incremental simplification, and verifies measurable architecture vector improvements while preventing refactoring theater.
---

# Architecture Refactor — Objective Debt Reduction

Use this skill when tasked with refactoring, simplifying, paying down technical debt, eliminating duplication, or improving codebase maintainability.

Refactoring without measurement frequently degenerates into **Refactoring Theater**:
- Splitting a 200-line file into five 40-line files connected by interfaces, which increases total system complexity and indirection while solving nothing.
- Adding wrapper layers, design patterns, or extra abstractions that make individual functions look smaller at the cost of global coupling.
- Moving complexity around rather than eliminating it.

This skill ensures refactoring is driven by **objective measurements and verified deltas**.

---

## Refactoring Hierarchy of Value

When refactoring, prioritize in this order:

1. **Deletion**: The cleanest code is code that doesn't exist. Delete dead branches, obsolete adapters, and unneeded state.
2. **Consolidation & Reuse**: Merge duplicate algorithms, clone groups, and redundant parsers into canonical implementations.
3. **Simplification**: Flatten deeply nested conditionals, reduce cyclomatic complexity (CCN), replace complex branching with simple lookup tables or direct early returns.
4. **Decoupling**: Eliminate circular dependencies, break structural chokepoints, reduce module fan-out.

**Strictly Avoid**:
- Splitting files purely for aesthetics.
- Introducing generic abstractions for single-use cases.
- Adding intermediate layers that just pass arguments through.

---

## Step-by-Step Refactoring Workflow

### Step 1: Establish Pre-Refactor Baseline
```json
call_mcp_tool(
  ServerName="architecture_fitness",
  ToolName="architecture_baseline",
  Arguments={"repo_path": "/path/to/repo", "name": "pre-refactor"}
)
```

### Step 2: Identify Measurable Hotspots
Retrieve the ranked list of architectural bottlenecks:
```json
call_mcp_tool(
  ServerName="architecture_fitness",
  ToolName="architecture_hotspots",
  Arguments={"repo_path": "/path/to/repo", "top_n": 10}
)
```
Each hotspot identifies:
- **Location**: Exact file, line range, and symbol name.
- **Kind**: `high_complexity` (CCN > 15), `duplication` (clones), `dependency_cycle`, `chokepoint`.
- **Score & Severity**: Prioritize CRITICAL and HIGH severity items.
- **Recommendation**: Concrete strategy to resolve the issue.

### Step 3: Select 1–2 High-Value Targets
Pick one specific hotspot to resolve first:
- *Target A: High CCN function*: Identify compound logic, nested loops, or excessive branching. Flatten the control flow.
- *Target B: Duplicate clone group*: Create a shared helper in an existing utility module and update both call sites.
- *Target C: Circular dependency*: Decouple imports or extract shared types.

### Step 4: Make Changes Incrementally
Edit the target code. Run local unit tests to ensure functional correctness.

### Step 5: Measure and Verify Improvement
Compare against baseline:
```json
call_mcp_tool(
  ServerName="architecture_fitness",
  ToolName="architecture_compare",
  Arguments={
    "repo_path": "/path/to/repo",
    "baseline_name": "pre-refactor",
    "diff_aware": true
  }
)
```

Verify that:
1. `ARCHITECTURE RESULT: IMPROVED` is achieved.
2. The targeted hotspot appears under **Existing problems resolved by this change**.
3. No **New problems** (e.g. accidental new clone groups or cyclomatic regressions) were introduced.

### Step 6: Retain or Revert
- If the change measurably improved the architecture vector and tests pass: **Retain**.
- If the change caused unintended regressions or had zero measurable benefit: **Revert** and reconsider your approach.
