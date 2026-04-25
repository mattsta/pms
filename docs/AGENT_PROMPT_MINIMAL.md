# Minimal Loop Prompt (Fast Intake)

Use this when you want a short intake and a quick loop start. It skips the
full interactive plan builder and only captures the minimum to get working.

Rules:

- PMS is the source of truth. Every task, goal, and update goes into PMS.
- Use `uv run pms` for all commands.
- Always update status, progress, and evidence as you work.

---

## Intake (ask first)

- Project name + product name
- One primary goal
- 3 to 7 acceptance criteria
- 5 to 15 tasks (short titles)

---

## Minimal setup commands

```bash
uv run pms product create "Resume Hosting"
uv run pms project create "Resume Hosting Site" --product "Resume Hosting"

uv run pms goal create "Launch resume hosting MVP" --project "Resume Hosting Site"
uv run pms objective create "MVP acceptance criteria" --goal "Launch resume hosting MVP"
uv run pms keyresult create "Landing page + upload flow" \
  --objective "MVP acceptance criteria" --goal "Launch resume hosting MVP"
```

Create tasks:

```bash
uv run pms task create "Resume Hosting Site" "Define UX and requirements"
uv run pms task create "Resume Hosting Site" "Implement upload API stub"
uv run pms task create "Resume Hosting Site" "Write README and run instructions"
```

Optional plan (minimal):

```bash
cat > plan.yml <<'EOF'
acceptance_criteria:
  - id: ac-1
    description: Landing page + upload flow
  - id: ac-2
    description: Upload API stub works locally
EOF

uv run pms plan create "Resume Hosting MVP Plan" \
  --project "Resume Hosting Site" \
  --goal "Launch resume hosting MVP" \
  --objective "MVP acceptance criteria" \
  --format yaml \
  --file plan.yml
```

---

## Minimal prompt template (PROMPT.md)

```
# Project
Resume Hosting Site (product: Resume Hosting)

# Goal
Launch resume hosting MVP.

# Acceptance Criteria
Tracked as key results under "MVP acceptance criteria".

# Loop Rules
1) Read PMS state first:
   - `uv run pms project show "Resume Hosting Site"`
   - `uv run pms goal list --project "Resume Hosting Site"`
   - `uv run pms objective list --goal "Launch resume hosting MVP"`
   - `uv run pms keyresult list --objective "MVP acceptance criteria" --goal "Launch resume hosting MVP"`
   - `uv run pms task list --project "Resume Hosting Site"`
2) Pick the next task, update progress, and complete it:
   - `uv run pms task start <task_id>`
   - `uv run pms task progress <task_id> <percent> <message> --by loop-agent`
   - `uv run pms task complete <task_id>`
3) Attach evidence for every task:
   - `uv run pms task evidence add <task_id> artifact <path>`
   - For tests: `uv run pms test run .` then
     `uv run pms task evidence add <task_id> test_run <run_id>`
4) Update key results and objective progress:
   - `uv run pms keyresult update <key_result_id> --goal "Launch resume hosting MVP" --progress <percent>`
   - `uv run pms objective update "MVP acceptance criteria" --goal "Launch resume hosting MVP" --progress <percent>`
5) When all key results are complete, complete the goal:
   - `uv run pms goal complete "Launch resume hosting MVP"`
6) When done, output <promise>DONE</promise>.
```

---

## Run the loop

```bash
uv run pms loop run --agent claude --project "Resume Hosting Site" \
  --prompt-file PROMPT.md \
  --completion-promise DONE
```
