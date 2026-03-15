---
name: react-ts-testing-practices
description: Best practices for React, TypeScript strict mode, and Vitest mocking learned from previous iterations. Use this when writing or refactoring React components or unit tests to prevent known regressions.
---

# React, TypeScript, and Testing Best Practices

These rules were empirically gathered from issue resolutions in strict-mode React single-page applications. Always adhere to these practices to prevent CI failures.

## TypeScript Strict Mode
- **RefObject Nullability:** Always allow `null` for React refs. Use `React.RefObject<HTMLDivElement | null>` rather than `React.RefObject<HTMLDivElement>` to comply with `strictNullChecks`.
- **Ref Initialization:** Use `import { createRef } from 'react'` and `createRef<T>()` rather than supplying manual objects like `{ current: null }`.
- **Type Imports:** Enforce `verbatimModuleSyntax` by strictly using type-only imports for types. Example: `import type { WorkflowState } from '../types'`.
- **No `any` Types:** Avoid `any` types to prevent runtime errors bypassing type safety. Always define proper interfaces or extract existing types.
- **Clean Imports:** Proactively remove unused imports after implementation. Strict ESLint rules will fail the build if unused imports remain.

## Test Mocking Patterns (Vitest / Jest)
- **Spying on Instances:** Do not create manual `axios.create()` mocks if a global `apiClient` singleton exists. Instead, use `vi.spyOn(apiClient['client'], 'get/patch/post').mockResolvedValue({data: ...})`.
- **Signature Matching:** Ensure mock return types flawlessly match actual function signatures. If an interface (e.g., `CommandIntent`) expects an `originalMessage` property, the mock object must explicitly supply it.
