# MCP Loop Prompt (PMS Tools Only)

Use this when the agent can only call MCP tools (no shell access). All actions
must use `mcp__pms__*` tools.

Rules:

- Always read PMS state before acting.
- Every task update must include progress and evidence.
- Use workflow assignment and transitions for each task.
- When all acceptance criteria are met, complete the goal.

---

## Tool names used

- Projects: `mcp__pms__create_project`, `mcp__pms__list_projects`
- Goals: `mcp__pms__create_goal`, `mcp__pms__list_goals`, `mcp__pms__get_goal`, `mcp__pms__get_goal_summary`, `mcp__pms__complete_goal`
- Objectives: `mcp__pms__create_objective`, `mcp__pms__list_objectives`, `mcp__pms__get_objective`, `mcp__pms__update_objective`
- Key results: `mcp__pms__create_key_result`, `mcp__pms__list_key_results`, `mcp__pms__update_key_result`
- Plans: `mcp__pms__create_plan`, `mcp__pms__list_plans`, `mcp__pms__get_plan`, `mcp__pms__update_plan`
- Tasks: `mcp__pms__create_task`, `mcp__pms__list_tasks`, `mcp__pms__update_task_progress`, `mcp__pms__start_task`, `mcp__pms__complete_task`
- Checkouts: `mcp__pms__checkout_task`, `mcp__pms__renew_task_checkout`, `mcp__pms__release_task_checkout`
- Evidence: `mcp__pms__add_task_evidence`
- Dependencies: `mcp__pms__add_task_dependency`, `mcp__pms__get_task_tree`
- Workflows: `mcp__pms__assign_workflow`, `mcp__pms__transition_workflow`

---

## Prompt template

```
You are running inside an MCP-enabled agent. Use PMS MCP tools only.

Project: Resume Hosting Site
Goal: Launch resume hosting MVP
Objective: MVP acceptance criteria
Plan: Resume Hosting MVP Plan

Loop Rules:
1) Read PMS state first:
   - mcp__pms__list_projects
   - mcp__pms__list_goals
   - mcp__pms__list_objectives
   - mcp__pms__list_key_results
   - mcp__pms__list_plans
   - mcp__pms__list_tasks
2) Assign workflow to tasks that need one:
   - mcp__pms__assign_workflow (entity_type=task, workflow_name=sdlc, initial_state=concept)
3) Check out and work:
   - mcp__pms__checkout_task
   - mcp__pms__start_task
   - mcp__pms__update_task_progress
   - mcp__pms__complete_task
4) Transition workflow as you advance:
   - mcp__pms__transition_workflow (idea -> planning -> implementing -> integration_testing -> production)
5) Add dependencies when ordering matters:
   - mcp__pms__add_task_dependency
   - mcp__pms__get_task_tree
6) Attach evidence for each completed task:
   - mcp__pms__add_task_evidence (artifact or test_run)
7) Update key results and objective progress:
   - mcp__pms__update_key_result
   - mcp__pms__update_objective
8) Validate the goal:
   - mcp__pms__get_goal_summary
   - mcp__pms__complete_goal when all criteria are met
```

---

## Example MCP tool calls (abbreviated)

```json
{"tool":"mcp__pms__create_project","input":{"name":"Resume Hosting Site"}}
{"tool":"mcp__pms__create_goal","input":{"name":"Launch resume hosting MVP","project_id":"<project-id>","horizon":"short_term"}}
{"tool":"mcp__pms__create_objective","input":{"goal_id":"<goal-id>","name":"MVP acceptance criteria"}}
{"tool":"mcp__pms__create_key_result","input":{"objective_id":"<objective-id>","name":"Landing page + upload flow"}}
{"tool":"mcp__pms__create_plan","input":{"name":"Resume Hosting MVP Plan","project_id":"<project-id>","goal_id":"<goal-id>","objective_id":"<objective-id>","format":"json","content":"{\"acceptance_criteria\":[{\"id\":\"ac-1\",\"description\":\"Landing page + upload flow\"}]}"}}
{"tool":"mcp__pms__create_task","input":{"project":"Resume Hosting Site","title":"Implement upload API stub"}}
{"tool":"mcp__pms__assign_workflow","input":{"entity_id":"<task-id>","entity_type":"task","workflow_name":"sdlc","initial_state":"concept"}}
{"tool":"mcp__pms__start_task","input":{"task_id":"<task-id>"}}
{"tool":"mcp__pms__update_task_progress","input":{"task_id":"<task-id>","percent_complete":50,"status_message":"Stub endpoint added","updated_by":"agent"}}
{"tool":"mcp__pms__complete_task","input":{"task_id":"<task-id>"}}
{"tool":"mcp__pms__add_task_evidence","input":{"task_id":"<task-id>","evidence_type":"artifact","reference":"src/upload.py","description":"Stub handler"}}
{"tool":"mcp__pms__update_key_result","input":{"key_result_id":"<key-result-id>","progress_percent":100}}
{"tool":"mcp__pms__complete_goal","input":{"goal_id":"<goal-id>"}}
```
