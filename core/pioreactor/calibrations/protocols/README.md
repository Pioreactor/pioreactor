# Calibration CLI UX Spec

This spec defines the CLI UX conventions for calibration flows. Apply these patterns consistently across all calibration scripts.

Use pioreactor.calibrations.cli_helpers to assist.

## Goals

- Keep calibration outputs unchanged (same computed results, same data structures).
- Make the CLI flow readable and consistent.
- Separate user input, information, and actions visually.

## Colors

Use pioreactor.calibrations.cli_helpers to get functions for these.

- User input prompts: green.
- Informational messages and headings: white.
- User actions (physical steps): cyan.
- Errors / aborts: red.

## Message Types

- **Info:** single-line status or explanation (white).
- **Heading:** key sections, white + bold + underline.
- **Action:** physical steps to perform, cyan.
- **Prompt:** questions or inputs, green.
- **Error:** aborts or invalid states, red.

## Spacing Rules

- Use an action block for physical steps, with a blank line before and after.
- Avoid stacking info, prompt, and action on the same line.
- When a prompt follows an action block, keep the blank line between them.

## Prompt Style

- Don't use a trailing colon for input prompts, e.g. `Enter OD600 measurement` .
- Use a question mark for confirmations, e.g. `Continue?`.
- Keep prompts short and specific.
- If the information is just pausing to start something, add `...` at the end. Example: "Warming up OD...", "Waiting for X..."

## Consistency Notes

- Prefer simple, direct language and consistent verbs (Enter, Confirm, Record).
- Avoid changing calibration behavior or output format.
- Reuse shared helpers for styling and spacing where possible.
