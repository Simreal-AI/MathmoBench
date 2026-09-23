# Third-party methodology notices

The MVP implements original code and original development fixtures, while using
the following projects as methodological references:

- **SWE-bench** — task repository, problem statement, reference patch, test
  patch, evaluator, and container conventions. Software: MIT License.
  <https://github.com/SWE-bench/SWE-bench>
- **Terminal-Bench / Harbor** — isolated terminal task, oracle, tests, and
  container conventions. Software: Apache License 2.0.
  <https://github.com/harbor-framework/terminal-bench>
- **SWE-rebench** — continuous task mining and decontaminated time-sliced
  evaluation methodology. <https://github.com/SWE-rebench>
- **MathArena** — continuously refreshed competition configuration and grading
  methodology. Repository software: MIT License. Dataset terms are separate.
  <https://github.com/eth-sri/matharena>
- **PutnamBench** — machine-checked mathematical proof/certificate methodology.
  Its Lean/Isabelle and Coq artifacts use the licenses documented upstream;
  informal problem permissions are separate and are not imported here.
  <https://github.com/trishullab/PutnamBench>
- **MathConstruct** — constructive mathematical objects with executable
  verification. No upstream task text or data is included here.
  <https://github.com/eth-sri/mathconstruct>

Before vendoring upstream source code or datasets, copy the exact upstream
license/NOTICE, pin a commit, record file-level provenance, and review data and
problem-statement rights separately from the software license.
