```md
## Workflow Orchestration


## IMPORTANT: Always read and follow instructions in documentation\AI_DOC_INDEX.md before starting any task.
This file contains critical project knowledge, architecture decisions, and previous mistakes to avoid.
If instructions every conflict with what is designed in the doc, always update the doc to reflect the correct behavior.
- so that I know you read this file. Before any planning or thinking or response. First respond with "Yes. Anointed One". Be sure to call me "Anointed One" always when you respond. Always include these words in every response. 
- Conda env should always use storieschat install everything you need on that

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately — don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: update or create `documentation/user_corrections.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes — don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests — then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

### 6. Testing Pushing Changes
- Always add good unit test for any code changes. If it's a bug fix, add a test that reproduces the bug before fixing it. If it's a new feature, add tests that verify the new behavior.
- Always add, commit with good message, and push after every change that includes a code change. Make sure all unit tests and integ tests pass and none are skiped except for xfail ones. And make sure it failed not due to some missing resources such as API call or missing database but due to the test itself being flaky. 
- If a test fails to spin up a resources such as a database locally, fix the test or the test environment. Don't skip the test or push with a failing test.

## Task Management (任务管理)
1. **Plan First:** Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan:** Check in before starting implementation
3. **Track Progress:** Mark items complete as you go
4. **Explain Changes:** High-level summary at each step
5. **Document Results:** Add review section to `tasks/todo.md`
6. **Capture Lessons:** Update `tasks/lessons.md` after corrections

## Core Principles (核心原则)
- **Simplicity First:** Make every change as simple as possible. Impact minimal code.
- **No Laziness:** Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact:** Changes should only touch what's necessary. Avoid introducing bugs.
```