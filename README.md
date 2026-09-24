# MathmoBench: Constraint-Shift Math

[![CI](https://github.com/Simreal-AI/MathmoBench/actions/workflows/ci.yml/badge.svg)](https://github.com/Simreal-AI/MathmoBench/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Status: public preview](https://img.shields.io/badge/status-public%20preview-34d399)](https://github.com/Simreal-AI)

> **Public preview · 公开预览版.** This repository is the open, minimal slice of MathmoBench: the grader, the validators, the agent-view projection, one randomized generator and ten development families. Hidden tracks (tasks, seeds and reference answers) are run by SimReal and are not in this repository. It is early and will change.
>
> 本仓库是 MathmoBench 的最小公开切片：评测器、验证器、agent 视图工具、一个随机题生成器和 10 个开发题族。隐藏轨道（题目、种子、参考答案）由 SimReal 运营，不在本仓库中。项目处于早期，会持续变化。
>
> Partner access · 合作接入: [business@simreal.co](mailto:business@simreal.co) · [github.com/Simreal-AI](https://github.com/Simreal-AI)

[中文](#中文) | [English](#english)

## 中文

MathmoBench 是一个**证书式评分**的组合数学推理评测。每个题族由 4 道相邻实例组成，它们只差一两处微小改动，结论却在可行与不可行之间翻转。被测模型必须给出机器可验证的证据：有解时给出解，无解时给出不可能性证明（Hall 障碍、团、奇圈、奇轮、容量下界等）。评分完全由确定性程序验证器完成，不使用 LLM 裁判。

本仓库包含评测器、验证器、agent 视图投影工具、随机匹配题生成器，以及 10 个 `public_dev` 开发题族。隐藏轨道（`static_hidden`、`fresh_private`）的题目、种子和参考答案不在仓库中。

> `public_dev` 题族只用于冒烟测试和调试提交格式，不作为排行榜成绩。

### 验证器

| 验证器 | 判定 / 优化目标 | 不可行或最优性证书 |
| --- | --- | --- |
| `bipartite_matching_v1` | 完美匹配判定、最大匹配 | Hall 子集；等大小最小顶点覆盖（König） |
| `subset_sum_v1` | 精确子集和判定、最接近子集 | 公约数障碍；超递增贪心余数 |
| `graph_coloring_v1` | k 着色判定、最小着色 | 团、奇圈、奇轮 |
| `bin_packing_v1` | 箱数上限判定、最少箱数 | 总容量下界；两两不兼容物品 |

### 快速开始

需要 Python 3.11+，无第三方依赖。

```bash
git clone https://github.com/Simreal-AI/MathmoBench.git && cd MathmoBench
python verify.py --run-tests
```

### 一次完整评测

```bash
export PYTHONPATH=src
mkdir -p run

# 1. 评测方生成题族（种子保密）
python -m mathbench.generator_cli --template matching --seed <私密种子> --size 64 \
  --output run/family.json

# 2. 导出 agent 视图；binding 只留在评测方
python -m mathbench.projection_cli run/family.json \
  --agent-view run/agent-view.json --binding run/binding.json \
  --salt "$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"

# 3. 只把 agent-view.json 交给模型，模型返回 run/submission.jsonl

# 4. 评分，输出带哈希的确定性回执
python -m mathbench.cli run/family.json run/submission.jsonl --binding run/binding.json
```

也可以 `pip install .`，然后使用 `mathbench`、`mathbench-generate`、`mathbench-export` 命令。

### 提交格式与评分

JSONL，每行一个对象，只允许 `instance_id`、`verdict`、`answer`、`certificate` 四个字段；各目标的格式见 agent 视图中的 `goal_contracts`。

单族得分 = 70 × 逐题正确率 + 30 × 整族全对。格式不合规的实例判为错误；未知、重复或缺失的实例 ID 使整族记零分并生成回执。评分政策以 `configs/protocol.json` 为唯一真源。

## English

MathmoBench is a **certificate-graded** benchmark for combinatorial reasoning. Each family holds four neighbouring instances that differ by one or two small edits yet flip between feasible and infeasible. Models must return machine-checkable evidence: a witness when a solution exists, and an impossibility proof when it does not (Hall obstruction, clique, odd cycle, odd wheel, capacity bound, and more). Grading is fully deterministic; there is no LLM judge.

This repository ships the grader, validators, agent-view projection, a randomized matching-family generator, and ten `public_dev` families. Hidden-track tasks, seeds, and reference submissions are not included.

> `public_dev` families are smoke fixtures for debugging pipelines and submission formats, not leaderboard results.

### Quick start

Python 3.11+, no third-party dependencies.

```bash
git clone https://github.com/Simreal-AI/MathmoBench.git && cd MathmoBench
python verify.py --run-tests
```

### End-to-end run

```bash
export PYTHONPATH=src
mkdir -p run
python -m mathbench.generator_cli --template matching --seed <secret> --size 64 --output run/family.json
python -m mathbench.projection_cli run/family.json \
  --agent-view run/agent-view.json --binding run/binding.json \
  --salt "$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
# give only run/agent-view.json to the model; it returns run/submission.jsonl
python -m mathbench.cli run/family.json run/submission.jsonl --binding run/binding.json
```

### Submissions and scoring

JSONL with exactly `instance_id`, `verdict`, `answer`, and `certificate` per line; per-goal shapes are in the agent view's `goal_contracts`.

Family score = 70 × per-instance accuracy + 30 × whole-family strict pass. Malformed instances score zero; unknown, duplicate, or missing IDs zero the family with a receipt. `configs/protocol.json` is the single source of truth for scoring policy.

## Part of SimReal

This repository is one public preview in the [SimReal](https://simreal.co) product line: environments where AI agents act and real outcomes decide the score. See every preview at [github.com/Simreal-AI](https://github.com/Simreal-AI).

## Integrity

`MANIFEST.sha256` pins every tracked file and `verify.py` checks it. After editing any file, regenerate the manifest (see `CONTRIBUTING.md`).

## License

Copyright 2026 Simreal-AI. Licensed under the [Apache License 2.0](LICENSE); see [`NOTICE`](NOTICE). Methodological references are listed in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
