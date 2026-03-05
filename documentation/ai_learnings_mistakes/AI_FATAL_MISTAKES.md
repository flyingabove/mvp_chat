AI Fatal Mistakes — Record of Production Incidents
====================================================
A running list of serious mistakes that caused production breakage.
Each entry documents what happened, why, what fixed it, and what
mitigations were added so it never happens again.


1.) BLANK PAGE — Orphaned Code Outside Function Scope (Feb 11 2025)
-------------------------------------------------------------------

WHAT HAPPENED:
  The frontend (storieschat.ai/beta/) loaded a completely blank black
  page. Only the bottom toolbar (input bar + Enter button) was visible.
  No terminal text, no menu, no error message — just black.

  The backend was healthy (deploy logs showed successful startup, tests
  passed, Uvicorn running). But HTTP logs showed zero requests, meaning
  the frontend JS crashed before it could even call the API.

ROOT CAUSE:
  During a refactoring of the `renderStepOutput` function in
  frontend/index.html, the function was rewritten to use a recursive
  `renderItem` inner function. The new version was correct.

  However, ~80 lines of the OLD function body were left behind OUTSIDE
  the function's closing brace. These orphaned lines sat between two
  function definitions, floating loose in the IIFE scope.

  The orphaned code referenced variables (`output`, `debug`) that only
  existed inside the old function. At page load, the JS engine hit these
  references, threw a ReferenceError, and killed the entire <script>
  block. Since everything (showMenu, event listeners, etc.) lived in
  that same script, the page rendered nothing.

WHY IT HAPPENED:
  - Copy-paste refactoring: the old logic was duplicated into the new
    recursive structure, but the original lines were not deleted.
  - The orphaned code looked plausible in a diff — it appeared to be
    the tail end of the function above it.
  - No syntax linter or build step exists for this single-file frontend.
    The code was pushed directly without any automated validation.
  - The AI editing the file replaced a block of code but did not verify
    what remained immediately below the edit boundary.

HOW IT WAS FIXED:
  Deleted the ~80 orphaned lines (everything between the closing brace
  of renderStepOutput and the next function definition). This was the
  only code change needed — the new recursive implementation was already
  correct.

  Commit: eb0fecd on beta branch.

MITIGATIONS ADDED:
  1. Early fatal-error guard: A separate <script> tag was added BEFORE
     the main IIFE. It sets window.__appBooted = false and listens for
     uncaught errors. If the main script crashes during initialization
     (before __appBooted is set to true), the guard:
     - Shows a visible error message in the #errbox div
     - Renders a fallback message in the #term div so the page is never
       completely blank
     This is a last-resort safety net — it does NOT prevent bugs, but it
     ensures users see an error message instead of a blank page.

  2. Documentation: AI_LEARNINGS_PUSHING_CODE.md was created with rules
     for AI to follow when editing single-file frontends:
     - Always check for orphaned statements after function refactors
     - Verify nothing sits between function definitions that doesn't
       belong there
     - Search for duplicate copies of old logic after copy-paste refactors

WHAT WOULD HAVE CAUGHT THIS:
  - Reading the file after editing and scanning for code between function
    definitions that isn't a declaration or assignment
  - A JS linter (eslint) with no-undef rule would have flagged the
    undefined `output` variable immediately
  - A simple `node --check frontend/index.html` syntax parse (though
    this wouldn't catch runtime ReferenceErrors from undefined vars in
    non-strict mode)
  - Any smoke test that loads the page and checks for basic DOM content
