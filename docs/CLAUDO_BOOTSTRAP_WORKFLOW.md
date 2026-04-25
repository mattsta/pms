# Claudo Existing Project Import

Use this when an existing project directory already has Claude todo state and
you want to bootstrap a project-local PMS database from Claudo.

Run the maintained script from the existing project directory:

```bash
cd /path/to/existing-project
~/repos/pms/scripts/import_claudo_existing_project.sh
```

Or pass the project directory explicitly:

```bash
~/repos/pms/scripts/import_claudo_existing_project.sh --project-root /path/to/existing-project
```

The script:

- requires the project directory to already exist
- forces PMS state to `$PROJECT_ROOT/.pms`
- creates `$PROJECT_ROOT/.pms/bootstrap`
- exports Claudo's full graph to a temporary file outside the project
- filters that export to Claudo sessions whose `project_path` or Claude
  `project_key` matches `$PROJECT_ROOT`
- writes the project-scoped graph to
  `$PROJECT_ROOT/.pms/bootstrap/claudo-project.graph.json`
- stops before import if no Claudo session matches the project directory
- dry-runs the PMS import before writing
- imports into the PMS project named after the project directory
- prints project, task, ready, and blocked views after import

For manual imports, pass `--project-root "$PWD"` to `pms claudo import` so PMS
filters the Claudo graph before writing.

Options:

- `--project NAME`: override the PMS project name.
- `--claudo-repo PATH`: override `~/repos/claudo`.
- `--claude-task-root PATH`: override `~/.claude/tasks`.
- `--session ID`: restrict the Claudo export to one Claude session; the script
  still verifies that session belongs to the selected project root.
