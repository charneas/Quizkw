---
name: frontend-test-helper
description: Guides conversational test creation for React components. Use when the user requests to 'write a test for a frontend component' or 'add testing for a component'.
---

# Frontend Test Helper

## Overview
This skill guides you through creating effective, resilient tests for React components using Vitest and React Testing Library. It optimizes the process by focusing on user-centric behavior, ensuring high-value coverage without excessive token usage.

Act as a Senior Frontend Engineer. Prioritize readable, resilient tests that maintain focus on actual component interaction.

## Routing
Start by asking the user which component they want to test.

## Activation
1. Identify the component path (e.g., `frontend/src/components/QuestionCard.tsx`).
2. Analyze the component:
   - Identify props and dependencies.
   - Look for interactive elements (buttons, inputs).
3. Plan scenarios:
   - What is the primary user interaction?
   - Define a small, high-impact set of tests (e.g., rendering, user interaction).
4. Generate the test file (typically `frontend/src/components/ComponentName.test.tsx`).
