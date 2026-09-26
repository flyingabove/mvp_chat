# BL-32 — Hosted simulator stays Connecting after initialization TypeError

- **Type:** bug
- **Found:** 2026-09-25, browser visit to `https://storieschat.ai/beta/debug`
- **Severity:** medium; browser playtest controls cannot initialize or explain the failure.

## Problem
Story selection is empty, models remain Loading, and status remains Connecting. Browser console: `TypeError: Cannot read properties of undefined (reading 'length') at init (https://storieschat.ai/beta/debug:1244:22)`. Source `frontend/debug.html` reads `data.stories.length` without guarding the response shape. The public story and chat APIs work independently; the actual simulator status response was not captured, so authorization versus another response failure is not established.

## Fix direction
Validate response status and payload shape before reading stories/models. Show an actionable authorized-login/operator or service-unavailable error as appropriate, with retry. Preserve operator protection. Cover successful, unauthorized and failed responses and verify the hosted page. Manual simulator `sendManual` also drops returned debug payloads and `exportLog` exports conversation only; consider complete operator-authorized recording in the same tooling follow-up.

## Why deferred / cautions
Review-only task; gameplay proceeded via the same live chat API with complete returned records. This was not a successful browser simulator run. Do not weaken authentication to make initialization succeed.

## Touches
`frontend/debug.html` (`init`, `sendManual`, `exportLog`), debug status endpoint and browser tests.
