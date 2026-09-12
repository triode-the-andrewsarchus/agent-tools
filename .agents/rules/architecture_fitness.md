# Architecture Fitness — Rules of Engagement

As an autonomous coding agent, you MUST follow these architectural fitness principles when reading, planning, writing, and refactoring code.

## 1. The Principle of Benefit of the Doubt
> **New mechanism requires justification; existing mechanism gets the benefit of the doubt.**

Before creating a new function, utility, data class, or configuration mechanism:
- Always check the existing repository architecture.
- Use `architecture_reuse_candidates` to discover pre-existing implementations.
- Extend or parameterize an existing function rather than adding a parallel implementation.

## 2. Accidental vs. Necessary Complexity
- **Necessary complexity**: Solving an inherently complex domain requirement. Acceptable and expected.
- **Accidental complexity**: Re-implementing logic that already exists, adding indirection layers without benefit, or introducing circular dependencies. Strictly unacceptable.

## 3. Anti-Gaming Heuristics
Never optimize metrics artificially:
- Moving lines of code to another file is **not** an architectural improvement.
- Splitting a cohesive function into 10 one-line wrappers increases indirection without reducing system complexity.
- Deleting necessary functionality to reduce lines of code is a failure.
- Introducing an overly generic abstraction just to remove a 3-line duplication can introduce more maintenance complexity than the duplication itself.
- Seek Pareto improvements across the multidimensional architecture vector.

## 4. Measurement Discipline
- Check architecture baselines before non-trivial changes (`architecture_baseline`).
- Verify structural deltas after modifications (`architecture_compare`).
- If `architecture_compare` reports `ARCHITECTURE RESULT: REGRESSION`, investigate whether the regression was truly necessary before finalizing your response.
