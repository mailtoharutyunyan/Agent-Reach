---
description: Scaffold a new WebLens platform channel following project conventions
agent: architect
subtask: true
---
Plan a new WebLens channel for: $ARGUMENTS

Study @weblens/channels/base.py and two existing channels first. The channel must be one file in `weblens/channels/`, inherit `BaseChannel`, implement `can_handle(url)`, `read(url)`, `search(query)`, `check()`, and only call the upstream tool through its public CLI/API (WebLens is a glue layer). Include doctor integration, tests, and docs updates in the plan.
