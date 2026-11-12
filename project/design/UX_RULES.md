# UX Rules

## General
- Show clear loading states.
- Show useful empty states.
- Show actionable error messages.
- Confirm destructive/irreversible operations.
- Preserve user input where possible after validation errors.
- Use server results as the source of truth after mutations.

## Business UX
Order lifecycle actions must reflect allowed transitions.
Payment UI must clearly distinguish pending, completed, failed and refunded states.
Financial values should be displayed consistently in Nigerian Naira.

## Navigation
Avoid placeholder `href="#"` links in production surfaces. Use real routes or explicitly mark a page as preview/demo.

## Accessibility
Use labels, semantic buttons, keyboard-accessible controls and appropriate ARIA attributes where needed.
