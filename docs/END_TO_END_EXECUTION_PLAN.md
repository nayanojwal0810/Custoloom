# Custoloom — End-to-End Execution Plan

## Project intent

**Working title:** Beyond Transactions: An Evidence-Grounded Customer Relationship Intelligence and Campaign Decision Engine

**Problem statement:** How can retail transaction and campaign-response data be used to identify interpretable customer relationship profiles, prioritize marketing interventions, and explore possible customer reactions through multi-agent simulation?

**Primary objective:** Build a reliable, reproducible analytical CRM project that demonstrates business analysis, analytics engineering, machine learning, explainable decisions, and careful use of simulation.

This is an execution plan. Claims and metrics will be included only after they are verified from source data and reproducible results.

## Agreed constraints

- Do not use the Olist dataset.
- No survey/questionnaire or manual customer study.
- Use PostgreSQL as the target analytical database.
- Use the existing X5 RetailHero dataset and code where valid; do not assume existing results are correct without revalidation.
- Use Hillstrom as a separate experimental benchmark if license/availability and target definitions check out. Never merge its customers with X5 customers.
- Keep the core pipeline CPU-capable. Use free Colab/Kaggle compute where practical; GPU is optional where it actually helps.
- MiroFish is an exploratory simulation module, not the project headline and not evidence of validated human prediction.
- Do not use synthetic values as if they were observed facts.
- Heavy commands and downloads are run by the user. Antigravity can inspect the workspace and suggest/read code; do not run expensive tasks without a clear approved step.
- No implementation changes until the current forensic findings and data assumptions are reviewed.
- Raw data, credentials, tokens, model secrets, and large dataset files must not be committed to GitHub.

## Target architecture

1. **Data sources**
   - X5 RetailHero: primary customer transactions and campaign treatment/outcome data.
   - Hillstrom: separate external benchmark for methods that fit its randomized campaign design.
   - Never join customers across datasets; report results separately.

2. **PostgreSQL analytical data platform**
   - Raw/staging tables.
   - Validated source tables and documented schemas.
   - Customer 360 and feature tables.
   - Model predictions/evaluation tables.
   - Decision outputs and BI marts.
   - SQL constraints/data checks and reproducible bulk loading.

3. **Analytics**
   - Data profiling and quality checks.
   - Spend, frequency, basket, recency, breadth and loyalty behavior where fields support them.
   - Explainable customer profiles, with thresholds defined from data and documented.
   - Business KPI analysis that does not imply causality without evidence.

4. **Machine learning, evaluated in stages**
   - Stage 0: transparent business-rule baseline.
   - Stage 1: simple, interpretable model where there is a valid target.
   - Stage 2: stronger tree-based model (e.g. LightGBM) if it improves held-out performance.
   - Stage 3: uplift model comparisons for incremental campaign response, only after treatment assignment and outcome definitions are verified.
   - Evaluate models with task-appropriate metrics, uncertainty and leakage checks. Keep a simple model if added complexity is not justified.

5. **CRM decision engine**
   - Map relationship profile, customer value and validated model signals to explicit actions.
   - Rules must be exhaustive, testable and explainable.
   - Avoid using one composite score as decoration; define what it means and how it affects decisions.
   - Distinguish likelihood to purchase from incremental treatment effect.
   - Actions such as loyalty rewards or cross-sell are recommendations/hypotheses unless directly evaluated by suitable data.

6. **MiroFish simulation experiment**
   - Test a small end-to-end simulation before scaling.
   - Create aggregate, data-grounded customer archetypes and comparable generic baselines.
   - Compare campaign/CRM scenarios with repeated runs.
   - Report simulated outputs as hypotheses, not observed customer outcomes or causal estimates.
   - Track configuration, model/provider, prompts, scenario inputs, run settings and costs.
   - Comply with upstream license and external service requirements.

7. **Power BI**
   - Deliver an actual interactive dashboard only after SQL outputs and decisions validate.
   - Show customer/portfolio profile distributions, value and campaign decision metrics, model comparisons and clearly labelled simulation results.
   - Reconcile visuals against source SQL and saved outputs.

## Execution phases and acceptance gates

### Phase 1 — Forensic audit of current project (NEXT)
Read-only assessment of:
- Data provenance, source documentation and target meanings.
- Treatment assignment and causal-validity evidence.
- Feature timing, split logic and leakage.
- Reproducibility of current uplift results.
- Model evaluation gaps (AUUC/Qini/uplift curves, calibration/uncertainty as appropriate).
- Decision rules, decile ranking, scoring logic and fall-through conditions.
- Current schemas, generated artifacts, missing tests and current execution assumptions.

**Acceptance gate:** A verified list of KEEP / REPAIR / REPLACE items with source evidence. Do not edit code or rerun expensive pipeline in this phase.

### Phase 2 — Correct and approve technical specification
- Correct any errors in the audit itself.
- Separate verified defects from assumptions.
- Define acceptance tests for every repair.
- Finalize target tables, pipeline flow and folder structure.

**Acceptance gate:** User approves the repair specification before implementation.

### Phase 3 — PostgreSQL proof of concept
- Confirm local/PostgreSQL or Colab connection approach.
- Create staging schema and data types.
- Test bulk load on a small sample first.
- Verify row counts, nulls, duplicate keys, referential integrity and date bounds.
- Load the full large file only after small-scale test passes and user runs the approved command.

**Acceptance gate:** Reproducible load and validation outputs. Do not require expensive compute for routine changes.

### Phase 4 — Customer 360 and analytical marts
- Rebuild Customer 360 in SQL.
- Parameterize the campaign/reference date rather than hardcode it.
- Handle single-basket customers explicitly without claiming reliable cadence where no cadence can be computed.
- Validate aggregation grain and reconcile sample calculations.
- Add data checks and tests.

**Acceptance gate:** Expected keys, counts, definitions and edge cases pass.

### Phase 5 — Baseline analytics and CRM profiles
- Establish KPIs and distribution summaries.
- Define usage, breadth, value and engagement dimensions supported by X5.
- Compare interpretable rule-based profiles and optional clustering.
- Produce exhaustive, mutually exclusive action mapping or explicitly documented multi-label actions.
- Test every rule branch and edge case.

**Acceptance gate:** No unexplained profile fall-through, contradictory decisions or unsupported experience-health fields.

### Phase 6 — Predictive and uplift modeling
- Reproduce a transparent baseline.
- Rebuild or verify the propensity models.
- Validate model features are pre-treatment.
- Compare T-learner with suitable simpler alternatives where appropriate.
- Evaluate with a held-out split and uplift curves/Qini/AUUC plus uncertainty.
- Assess policy performance at multiple targeting budgets against random and propensity-based targeting.
- Save model artifacts, configuration, prediction outputs and evaluation reports.

**Acceptance gate:** Results can be reproduced; causal wording matches the experiment design; all comparisons use consistent held-out evidence.

### Phase 7 — Independent benchmark
- Profile Hillstrom data and confirm schema/license/target semantics.
- Implement only the corresponding compatible methods.
- Evaluate it separately from X5.
- Explain differences in populations, outcomes and campaigns.

**Acceptance gate:** Independent test results are reported separately with no cross-dataset customer joins.

### Phase 8 — Decision policy
- Map validated profiles and uplift estimates to transparent actions.
- Make constraints and trade-offs explicit (budget, target share, estimated incremental response).
- Use expected value only if costs/revenue assumptions are documented.
- Include abstain/insufficient-evidence conditions.

**Acceptance gate:** Decision output has a reason, supporting metrics and clear caveats.

### Phase 9 — MiroFish prototype and experiment
- Verify upstream repository requirements and license.
- Configure secrets without committing them.
- Run the smallest end-to-end scenario in Colab.
- Compare generic versus data-grounded archetypes.
- Repeat scenarios to assess stability and sensitivity.
- Record costs and compute limits.
- Keep simulation outputs separate from observed and ML-predicted data.

**Acceptance gate:** The actual end-to-end run works, experiment is repeatable, and outputs are clearly labelled as simulated.

### Phase 10 — Power BI and integrated QA
- Build and save the actual report.
- Validate every major visual against SQL aggregates.
- Test filters, totals, labels, missing values and action explanations.
- Run core pipeline steps from documented instructions.
- Add automated data/model/decision tests where feasible.

**Acceptance gate:** Final numbers reconcile and pipeline is reproducible within normal CPU/free notebook limits.

### Phase 11 — Only after project works
- Finish GitHub README and environment instructions.
- Prepare architecture documentation, model cards, data dictionary and limitations.
- Prepare final course report and presentation.
- Write resume bullets only from measured, reproducible outcomes.
- Evaluate publication opportunities based on the final methodology and results; publication is not guaranteed.

## First concrete task for Antigravity

Run the separate prompt supplied in the conversation for **Task 1 — Forensic Validation of OptiSpend Engine**. Keep the workspace read-only. Do not fix bugs, modify code, download data, install packages, or run full training. Provide exact file/line evidence and distinguish facts, assumptions, and unknowns.

## Shared development workflow

- User downloads datasets into the local data folder and runs heavy/long commands.
- Colab clones this GitHub repository for notebook development and pushes code/result artifacts that are small and appropriate for version control.
- Antigravity pulls the repository and inspects the actual files.
- The assistant independently evaluates shared source code, logs and outputs.
- Large raw datasets, credentials, service keys, and large binary artifacts stay out of Git; use instructions and checksums instead.
- Use small commits with clear messages; do not mix unreviewed destructive changes into the default branch.

## Core principles

1. Evidence over impressive claims.
2. Business problem before model choice.
3. Simple baselines before complex models.
4. Predictions, causal effects and simulations remain distinct.
5. Every action recommendation must be explainable.
6. Reproducibility and validation are part of the project, not final cleanup.
7. No changes occur before the relevant approval gate.
