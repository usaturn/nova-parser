# Data Model: Devcontainer で Spec Kit を Copilot 運用に載せる

## WorkspaceState

- 目的: 導入状態の可視化
- 属性:
  - tool_available
  - initialized
  - prerequisite_status
  - reproducibility_confirmed

## FeatureTicket

- 目的: feature 管理
- 属性:
  - feature_number (`003`)
  - short_name (`copilot-spec-kit`)
  - branch_name (`003-copilot-spec-kit`)
  - spec_file (`specs/003-copilot-spec-kit/spec.md`)
  - plan_file (`specs/003-copilot-spec-kit/plan.md`)
  - tasks_file (`specs/003-copilot-spec-kit/tasks.md`)

## ChatCommandRoute

- 目的: Copilot Chat 導線管理
- 属性:
  - command_name
  - prompt_file
  - agent_file
  - expected_result
