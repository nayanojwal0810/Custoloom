# Custoloom — Final Beginner-Friendly End-to-End Execution Plan

**Project name:** Custoloom  
**Working title:** Retail Customer Intelligence and Campaign Decision Engine  
**Purpose of this file:** This is the single project blueprint. Read it before implementation. Every task must map to a business question, a skill, a tangible output, a validation check, and an approval gate.

---

## 0. First, understand what we are building

### The project in one sentence

Custoloom will use retail transaction and campaign data to help a retailer understand customers, evaluate marketing campaigns, and make better decisions about which campaign to test or target—while clearly explaining the evidence and limitations.

### The business story

Imagine a grocery retailer has loyalty customers and millions of transaction rows. The marketing team can send a campaign, but reaching everyone can cost money and annoy customers. The team needs to answer:

1. What does customer shopping behaviour look like?
2. Which customer groups behave differently, and what evidence supports those differences?
3. Did a campaign appear to change customer behaviour, or would those customers likely have purchased anyway?
4. Which customers should be prioritized if the retailer can contact only a limited share of its audience?
5. What can the data support, what remains uncertain, and what should the business test next?
6. Can a scenario simulator such as MiroFish help brainstorm communication risks or testable hypotheses without pretending its simulated agents are real customers?

The final system should turn data into a defensible recommendation. It is not just a collection of SQL scripts, model notebooks, and charts.

### What a hiring manager should see

A reviewer should be able to follow one coherent chain:

**Business question → source data → SQL/data quality → EDA → business insight → customer/campaign analysis → evaluated model → decision recommendation → dashboard → tested limitations.**

The project should show that the owner understands both the technical calculations and their business meaning. A tool is included only when it does useful work in this chain.

### What Custoloom is not

- It is not a claim that a model can predict every customer's behaviour with certainty.
- It is not a collection of charts with no business decision behind them.
- It is not a reason to use every popular tool regardless of fit.
- It is not allowed to treat simulated MiroFish output as observed customer data or proof of campaign impact.
- It will not make claims about incremental revenue or profit unless the available data and explicitly stated assumptions support them.

---

## 1. The MiroFish decision — honest fit assessment

### What MiroFish actually does

The official MiroFish project describes a workflow that starts from source material, builds a knowledge graph and agent profiles, runs a multi-agent social simulation, and produces a report that can be explored further. Its official repository presents examples such as public-opinion scenarios and fictional/creative simulations. The demo URL provided for review is described by the official FAQ as a static, prebuilt demonstration page—not a live model service that accepts arbitrary Custoloom data. Fixed demo responses are expected.

Official references:

- Main repository and overview: https://github.com/666ghj/MiroFish
- Demo shared by the user: https://666ghj.github.io/mirofish-demo/
- Official FAQ and scope/limitations: https://github.com/666ghj/MiroFish/issues/726
- License: https://github.com/666ghj/MiroFish/blob/main/LICENSE

The official FAQ explicitly cautions that MiroFish should not be equated with a scientifically calibrated classical agent-based model. Its output does not automatically have calibrated confidence, predictive validity, or causal validity. Serious conclusions require baselines, repeated runs, independent checks, and appropriate evidence. It also states that running the actual application requires a self-hosted setup, supported runtime dependencies, an LLM provider, and Zep configuration; the demo alone is not an end-to-end experiment.

### Is it a perfect fit for retail CRM?

**No. It is not a good fit for the core CRM targeting or uplift-modeling job.** MiroFish does not replace SQL analysis, a properly evaluated statistical model, a valid experiment, or an uplift policy. It must not decide who will buy or whether a campaign caused a purchase.

It has a narrower possible role: **exploratory campaign-communication scenario testing**. For example, after real analysis identifies a customer segment and the business drafts two loyalty campaign messages, we can explore how synthetic agents with clearly described assumptions discuss the messages, what objections appear, and what questions might be worth testing with real customers. This is brainstorming and risk discovery—not evidence of real customer preference.

### MiroFish go/no-go rule

MiroFish will be a *conditional, small experiment*, not a dependency of the main product.

We will not install or integrate it during the early phases. First, Custoloom must have reliable data, documented EDA findings, a campaign-analysis result, and at least one concrete campaign decision question. Then we will run a small pilot only if the required environment and API costs are practical.

The pilot compares:

- **Baseline A:** a campaign scenario described using generic, non-data-specific assumptions.
- **Scenario B:** the same campaign question enriched with Custoloom's verified, aggregated segment findings and clearly labelled assumptions.

The two scenarios must use the same business question and comparable settings. Run multiple repetitions where feasible and record model/provider, prompt, input documents, version, configuration, runtime, and costs. Review the outputs using a pre-defined rubric:

1. Did the simulation surface a concrete, testable concern or hypothesis?
2. Was the insight already obvious from the EDA or business analysis?
3. Can the finding be traced to provided source material, or is it an unsupported agent-generated idea?
4. Did it change the proposed message, campaign guardrail, or real-world test design?
5. Were results materially different across repeated runs?
6. Was the added usefulness worth the setup effort and cost?

**Keep MiroFish in the final project only if the pilot produces a useful, clearly documented contribution.** If it produces generic storytelling, unstable or untraceable claims, no change to the decision, or excessive cost, remove it from the core project. At most, document the negative result as an optional experiment. That is more credible than forcing a poor-fit tool into the flagship project.

The MiroFish output will never be entered into the campaign outcome table as a real response, used as a model training label, or presented as a calibrated forecast.

---

## 2. Principles that apply to every phase

1. **Beginner clarity is part of the acceptance criteria.** Before a task starts, explain its goal, inputs, operations, outputs, and why the work is needed in simple language.
2. **No blind prompt copying.** The user should know what Antigravity is being asked to change and what a successful result looks like before running a prompt.
3. **One approved phase at a time.** Do not move to the next phase until the previous phase's evidence is reviewed and the user explicitly approves it.
4. **Evidence, not claims.** Test counts, data totals, model scores, and findings must come from actual command output, executed queries, or saved artifacts. Never invent or copy expected values into results.
5. **Do not carry forward historical results as accepted truth.** After the reset, old code, tables, screenshots, metrics, model results, and reports are not evidence. Source datasets may be reused only after their provenance and contents are independently verified.
6. **Do not build for tool count.** SQL is for reliable data work; Python is for analysis/modeling/pipelines; visualizations answer specific questions; Power BI supports decisions; MiroFish gets only the limited role described above.
7. **Simple baseline before complex model.** Complexity must improve useful held-out performance or decision quality.
8. **No causal claim without a defensible design.** Treatment/control labels and balanced features alone do not prove random assignment or causal validity.
9. **No visual without a question.** Each chart must have a title, units, appropriate scale, a source query, an interpretation, and a decision or learning implication.
10. **Protect data and credentials.** Do not commit raw datasets, persistent database files, `.env`, API keys, private customer-level outputs, or large generated files to GitHub.
11. **Keep the pipeline reproducible and affordable.** Test with small fixtures first. Never reload tens of millions of rows to test a small code change.
12. **Use honest fallback decisions.** If a dataset field, experiment design, package, or tool cannot support the intended analysis, revise the plan before proceeding rather than force an unsupported result.

---

## 3. Roles and working method

### User / project owner

- Keeps source data backed up outside the repository and runs heavy local commands when asked.
- Reads the phase explanation and asks questions before approving work.
- Reviews outputs with the assistant and approves the next phase.
- Learns to explain the business reason and interpretation—not only run the commands.

### Antigravity

- Inspects and edits the local workspace when explicitly asked.
- Implements only the agreed scope.
- Runs the tests and commands named in the approved task and returns actual outputs.
- Shows files changed, key code decisions, data results, failures, and Git state.
- Does not redesign the full project, delete unrelated files, download large data, spend money, or start the next phase without authorization.

### ChatGPT reviewer / planner

- Explains concepts and task value in plain English before implementation.
- Writes scoped Antigravity prompts only after the task is understood.
- Reviews code, queries, calculations, test output, analysis interpretation, and business claims.
- Distinguishes verified facts, hypotheses, unknowns, and recommended changes.
- Does not mark a phase complete just because Antigravity says it is complete.

### Required cycle for every phase

**Explain → agree on acceptance criteria → write one focused prompt → inspect plan/scope → implement → inspect actual outputs → independently review → user understands the result → user approves next phase.**

If Antigravity starts editing before explaining a material ambiguity, pause and request a plan rather than continuing blindly.

---

## 4. Fresh-start and repository-reset policy

The user plans to start with a clean working tree and retain only this plan under `docs/END_TO_END_EXECUTION_PLAN.md` initially.

### Before removing files

- Confirm this exact plan exists at the intended local path and is readable.
- Make a dated backup *outside* the repository of any raw source datasets or files that cannot be re-downloaded. This backup is for data safety only; it does not make old outputs authoritative.
- Identify whether the `.duckdb` file contains only derived tables. It can be recreated from source data; do not treat it as the trusted starting point.
- Confirm no secrets or data that need emergency revocation are being overlooked.
- Confirm the intended Git state: deleting files from the working tree and committing the deletion does **not** erase prior Git history. If there are old secrets in history, use a separate secret-remediation procedure; never assume deleting the file is enough.

### Reset target

After the user performs/approves the reset, the working tree should contain only:

```text
docs/
└── END_TO_END_EXECUTION_PLAN.md
```

Keep `.git` metadata so the repository remains a Git repository. Do not erase the remote repository or rewrite shared history unless the user explicitly approves that separate destructive operation.

The raw source datasets should remain outside the repository during reset. Later, a new `.gitignore` and clean folders will be deliberately created in the scaffolding phase. Never run a broad delete command without first listing exactly which paths will be removed and confirming the plan file and source-data backup are safe.

### Fresh-start rule

After reset, don't use old schema assumptions, old table counts, old SQL, old model metrics, old test totals, or old persona rules as evidence. Re-read the dataset's official documentation and inspect the files that actually exist. Reuse a design only when this fresh verification supports it.

---

## 5. Target architecture and repository layout

We will use **Python + DuckDB + SQL + pandas + a plotting library + scikit-learn/appropriate uplift tooling + Power BI**, with optional Colab for bounded compute. DuckDB is chosen as a practical local analytical database for large tabular analysis. We will not add PostgreSQL merely to make the stack look bigger; a second database is justified only if it solves an actual delivery requirement.

The final layout can evolve, but each folder must have a purpose:

```text
Custoloom/
├── docs/
│   ├── END_TO_END_EXECUTION_PLAN.md
│   ├── DATA_DICTIONARY.md
│   ├── METRIC_DEFINITIONS.md
│   ├── MODEL_CARD.md
│   ├── DECISION_POLICY.md
│   └── MiroFish_PILOT.md                 # only if the pilot is run
├── data/
│   ├── raw/                              # ignored by Git; sourced files only
│   └── processed/                        # ignored by Git; recreated database
├── sql/
│   ├── 01_source_profile.sql
│   ├── 02_quality_checks.sql
│   ├── 03_customer_marts.sql
│   ├── 04_eda_queries.sql
│   └── 05_campaign_evaluation.sql
├── src/custoloom/                         # small reusable pipeline modules
├── notebooks/
│   ├── 01_data_quality_and_eda.ipynb
│   ├── 02_campaign_analysis.ipynb
│   └── 03_model_evaluation.ipynb          # only after model design is approved
├── reports/
│   ├── figures/                           # reviewed charts exported from notebooks
│   ├── sql_results/                       # small, safe aggregate query results
│   ├── analysis/                           # durable findings with evidence
│   └── model_evaluation/                   # evaluation tables and figures
├── powerbi/                               # report and setup notes; PBIX handling documented
├── tests/                                 # small synthetic and integration tests
├── .env.example                           # placeholders only, no secrets
├── .gitignore
├── pyproject.toml / requirements.txt
└── README.md                              # polished only after working evidence exists
```

Do not create every listed file at the beginning. Create files when their phase arrives. In particular, don't write the final README, executive report, model card, or resume bullets using results that don't yet exist.

---

## 6. Skills map — exactly where each skill must be demonstrated

| Skill | Where it is used | Evidence required in the repository | What it proves |
|---|---|---|---|
| Business framing and KPI design | Phase 1 | Problem statement, metric definitions, constraints, decision log | Understands what the company needs to decide |
| Data sourcing and data governance | Phase 2 | Source register, license/attribution, file manifest and checksums | Knows where data came from and what can be shared |
| Python fundamentals | All pipeline/notebook phases | Readable modules, functions, clear error handling, notebooks | Can use Python to complete real analytical work |
| SQL | Phases 3–6, 9–12 | Executed `.sql` files, saved result tables/CSV and query explanations | Can query, transform and validate data rather than hide results in code |
| Data engineering | Phases 3–5 | Reproducible ingest/build scripts, staging/fact/mart tables, data quality tests | Can turn raw files into reliable analysis-ready data |
| EDA and statistics | Phase 6 | Executed notebook, exported PNG/SVG figures, summary table, written findings | Can understand distributions and avoid misleading interpretation |
| Business/Data Analytics | Phases 6–7 | Insight register mapping evidence to business action | Can turn patterns into meaningful recommendations |
| Segmentation / CRM | Phase 8 | Segment definitions, population breakdowns, action mapping and edge-case tests | Can create explainable customer actions instead of arbitrary labels |
| Machine learning | Phases 9–10 | Baseline/candidate comparison, split design, metrics and error analysis | Can train and evaluate models appropriately |
| Causal/uplift analysis | Phase 10, only if supported | Experiment audit, uplift curves/Qini or suitable metric, uncertainty, targeting-policy comparison | Understands incremental effect versus ordinary response likelihood |
| Decision science / optimization | Phase 11 | Policy table, budget/targeting scenarios, assumptions and sensitivity analysis | Can support a real decision with trade-offs |
| Multi-agent AI / MiroFish | Conditional Phase 12 | Pilot protocol, scenario inputs, repeated outputs, review rubric and go/no-go conclusion | Can evaluate an AI simulation critically rather than trust its story |
| Power BI | Phase 13 | `.pbix`, data model, measures, screenshots and SQL reconciliation checks | Can communicate the decision and evidence to business users |
| Testing and reproducibility | Throughout | Tests, command log, environment instructions, repeatable steps | Can make the results trustworthy and inspectable |
| Git/GitHub | Throughout and final phase | Small focused commits, clean status, no secrets or raw data | Can collaborate and maintain a project professionally |
| Technical/business communication | Final phase | Architecture, model/policy explanations, project demo and resume evidence | Can explain why a result matters and what its limitations are |

**Skill usage rule:** We don't have to mention a skill in the README merely because it was installed. We have to show an artifact where the skill performed meaningful work.

---

# Execution phases

Each phase below has a beginner explanation, tasks, deliverables, quality checks, and an approval gate. The phase is not complete until the gate passes.

## Phase 0 — Reset and establish project control

### In simple words

We remove old implementation files from the working tree so we're not confused by old assumptions. We retain this plan and preserve the raw source data outside the repository. A clean repository is the starting point—not proof that the underlying data has been verified.

### What we will do

1. Confirm `docs/END_TO_END_EXECUTION_PLAN.md` is the exact plan to retain.
2. Make a file listing before deletion and a dated external backup of source files that cannot be replaced.
3. Identify generated databases, caches, logs, exports, code, notebooks, tests and configuration files that are to be removed from the *working tree*.
4. Show the user an exact deletion list before destructive commands are run.
5. After approval, remove all working-tree content except the plan. Keep Git metadata and do not rewrite repository history by default.
6. Verify the retained tree, `git status`, current branch and remote before making the reset commit.

### Skills used

Git hygiene, data/secret safety, reproducible-workspace management.

### Required output/evidence

- Retained plan exists and opens correctly.
- Exact before/after file tree.
- A reset record stating what was removed and what was intentionally kept.
- Clean or clearly documented Git state.

### Completion gate

The user confirms that the retained files are correct and that source data needed later is backed up. **No code, ingestion, or analysis starts in this phase.**

---

## Phase 1 — Understand the business decision before touching data

### In simple words

Before choosing models or drawing charts, we decide what the retailer needs help with. A good project answers a decision question; it does not start with “let's use machine learning.”

### Main business question

**How should a retailer use available customer and campaign data to prioritize CRM campaigns responsibly and learn whether those campaigns create incremental customer response?**

### What we will do

1. Define the user of the system: a CRM/marketing manager.
2. Define the decision: which eligible customer group to prioritize for a future campaign or test, subject to an explicit contact/targeting limit.
3. Define outcomes supported by the data. Possible primary outcome: the campaign target/outcome field in the dataset, once its official meaning is verified. Revenue/profit outcomes may be used only if suitable observed measures and costs exist.
4. Define what “better” means. Candidate measures include incremental response per targeted customer, uplift at the top X% of ranked customers, campaign reach, and estimated net value only if costs and monetary assumptions are supported.
5. Record business constraints: no real deployment to customers; recommendations are analytical proposals; all causal statements require evidence.
6. Create a one-page decision brief with the primary question, secondary questions, user, target population, available decisions, candidate KPIs, and known unknowns.

### Skills used

Business analysis, KPI design, stakeholder-style problem framing, analytical thinking.

### Required outputs

- `docs/PROJECT_BRIEF.md`
- `docs/METRIC_DEFINITIONS.md` with candidate metrics clearly marked provisional until source semantics are confirmed
- A decision log separating facts, assumptions and open questions

### Completion gate

The user can explain in their own words what the business decision is and how the project results would help. No model choice is approved until its purpose links to this decision.

---

## Phase 2 — Identify and verify the source datasets

### In simple words

We find out exactly what each file contains, where it came from, what each row means, and which questions it can answer. We do not assume old data descriptions are correct.

### What we will do

1. Identify the intended primary dataset (expected to be the X5/RetailHero retail campaign dataset, subject to fresh verification of the actual files and source documentation).
2. Record original download/source URL, access date, license/terms, file names, file sizes and checksums.
3. Inspect each file's header, encoding, compression, delimiter, inferred data types and a tiny sample. Never print large customer-level extracts in the report.
4. Read the authoritative dataset documentation for treatment flag, target/outcome meaning, observation periods, and intended train/test usage. Do not infer random assignment from a 50/50 split alone.
5. Confirm transaction, basket, customer, product and campaign grains. “Grain” means what one row represents.
6. Decide which files are safe and necessary to retain locally and which are too large/private for Git.
7. Record uncertainty explicitly when documentation is missing or ambiguous.

### Skills used

Data sourcing, Python file inspection, data governance, schema discovery, business understanding.

### Required outputs

- `docs/DATA_SOURCE_REGISTER.md`
- `docs/DATA_DICTIONARY.md` with field, type, meaning, unit, key/grain and known limitations
- `reports/analysis/source_file_manifest.csv` (small manifest only; no customer data)
- A short source verification report stating what the data supports and does not support

### Completion gate

Every file used downstream is accounted for; the campaign outcome and treatment semantics are documented or formally marked unresolved. If the experiment protocol cannot be verified, the uplift phase must be revised before implementation.

---

## Phase 3 — Build a clean, reproducible environment

### In simple words

We set up a project that can run again without relying on someone else's local paths, hidden packages, or undocumented manual actions.

### What we will do

1. Create the smallest required project structure and `.gitignore` before putting raw data into the repository.
2. Set up a Python environment using the project's documented Python version and dependency manager.
3. Configure a local DuckDB database path outside Git-tracked files.
4. Add environment configuration examples containing placeholders only. No real API keys or passwords.
5. Test that the application can import its modules and connect to an empty temporary database.
6. Add commands to print helpful setup checks and fail clearly when configuration is missing.

### Skills used

Environment management, clean code organization, DuckDB setup, Git and secrets management.

### Required outputs

- `.gitignore`
- `pyproject.toml` and/or `requirements.txt` (avoid redundant conflicting dependency sources)
- `.env.example` only if configuration variables are genuinely required
- `src/custoloom/config.py` and a small database connection module when needed
- `tests/test_config.py` and `tests/test_db.py`
- A setup guide added to README later or captured in `docs/SETUP.md` while the project is being built

### Completion gate

A clean environment can import the package and connect to a temporary DuckDB database. Raw data, generated database files, credentials and machine-specific paths are not tracked by Git.

---

## Phase 4 — Ingest source files with SQL-ready staging tables

### In simple words

We move data from the source files into DuckDB without changing its meaning. This is like arranging ingredients before cooking: we want to preserve the source and record how it was loaded.

### What we will do

1. Define staging table columns and appropriate data types based on Phase 2—not solely on automatic inference.
2. Ingest a small sample first and inspect the loaded values.
3. Load the complete source data only after the sample is validated and the user approves the full load.
4. For large compressed transaction files, use a streaming/bulk-load method suitable for available memory. Avoid reading tens of millions of rows into one giant Python object.
5. Preserve a reliable source-row identifier for each raw transaction line where necessary. Do not deduplicate based on a seemingly natural key unless the dataset specification says it is unique.
6. Record source file checksums, load time, source row count, loaded row count, and any rejected rows.
7. Make ingestion safe to rerun: define whether a run replaces staging tables or appends only when source identity makes that safe.

### Skills used

SQL DDL, Python I/O, bulk loading, data types, reproducibility, memory awareness.

### Required outputs

- `sql/01_create_staging_tables.sql`
- `src/custoloom/ingest.py`
- `reports/sql_results/staging_row_counts.csv`
- `reports/sql_results/staging_schema.csv`
- `reports/analysis/ingestion_run_log.md`
- Tests using tiny synthetic files; no large file ingestion during unit tests

### Completion gate

Source and loaded row counts reconcile or all differences are explained. Types, key behavior and sample values are checked. Full ingestion is repeatable and the raw source files remain unchanged.

---

## Phase 5 — Data quality and source-of-truth checks

### In simple words

A database can load successfully and still be wrong. This phase checks if the data is complete, consistent and at the expected level of detail. We catch errors before they become misleading charts or models.

### What we will do

Run focused SQL checks for:

- Row counts and duplicate keys at the documented grain.
- Null and blank values in important keys.
- Missing foreign keys, such as transaction lines pointing to absent clients/products.
- Date ranges, out-of-window dates and impossible date orderings.
- Numeric domains, negative quantities or prices where disallowed by the data definition.
- Transaction/basket invariants: values repeated on each line of the same basket must agree before we aggregate them.
- Exact duplicate rows versus legitimate repeated products or line combinations.
- Unexpected categories, invalid codes, encoding issues and unusual distributions.
- Treatment/outcome value counts and missingness, without claiming random assignment yet.

For each check, save the SQL and the result, not just a sentence that says “quality passed.” A failing check must produce a useful exception or a documented, approved disposition; it must not quietly pass.

### Skills used

SQL aggregates, joins, CTEs, window functions where helpful, data-quality design, Python testing.

### Required outputs

- `sql/02_data_quality_checks.sql`
- `src/custoloom/quality.py` only for reusable orchestration, not duplicated hard-coded results
- `tests/test_quality.py`
- `reports/sql_results/quality_check_summary.csv`
- `reports/sql_results/quality_issues.csv` with issue type, count and severity; no unnecessary customer identifiers
- `docs/DATA_QUALITY_REPORT.md` explaining the impact of any issue

### Completion gate

Critical tests pass; unresolved defects and exceptions are documented. A failing or unexplained data-quality result blocks the mart, EDA and model phases.

---

## Phase 6 — Build the analytical data model and Customer 360 using SQL

### In simple words

Raw files are not easy to analyze directly. We build a small number of clean, well-defined tables, including one row per customer with useful shopping measures. This avoids recalculating metrics differently in every notebook.

### What we will do

1. Build a documented basket/fact layer at the correct transaction grain.
2. If a transaction-level spend value is repeated on each product line, validate the basket invariants first and aggregate at basket level before aggregating to customer. Never sum a repeated basket total once per product line.
3. Build a customer-level mart with one row per eligible customer, preserving customers without transactions if the business question requires them.
4. Choose an explicit observation cutoff date and ensure every feature is measured only from data available before the outcome window.
5. Calculate measures supported by the source, such as total baskets, total spend, average basket value, recency, frequency, recent spend, category breadth, and store concentration. Define each in `METRIC_DEFINITIONS.md`.
6. Keep campaign outcome/treatment fields out of general pre-treatment features. Store labels in a separate, appropriately keyed campaign table.
7. Compare independent hand-calculations for a tiny sample of customers against SQL outputs.
8. Validate row count, primary-key uniqueness, cutoff dates and aggregate spend reconciliation.

### Skills used

SQL joins, aggregation, grouping, date logic, CASE expressions, window functions when necessary, dimensional/analytical modeling and business metric definition.

### Required outputs

- `sql/03_build_customer_marts.sql`
- Fact/basket layer and `mart_customer_360` (exact names to be approved after source inspection)
- `docs/METRIC_DEFINITIONS.md`
- `reports/sql_results/customer_360_profile.csv`
- `reports/sql_results/customer_360_reconciliation.csv`
- `tests/test_customer_mart.py`

### SQL evidence requirement

A reviewer must be able to open the `.sql` scripts, run the documented query, inspect the saved result, and understand what the result means. SQL is not considered “shown” simply because it exists inside a Python string.

### Completion gate

Every mart has an explicit grain and key. Customer coverage and totals reconcile to a source-of-truth SQL result. Feature dates precede target outcomes. No EDA chart or model can use an unvalidated mart.

---

## Phase 7 — EDA: explore the data and create real visualizations

### In simple words

EDA means Exploratory Data Analysis. We inspect the data to understand what is normal, what is unusual, what patterns exist, and which questions deserve deeper analysis. This is where we prove that we can “understand data,” not just process it.

### How we will work

1. Use SQL for repeatable summaries and pandas for notebook exploration.
2. Ask a question before making each chart. For every figure, note the query/source, sample size, units, and relevant data exclusions.
3. Use appropriate axes and scales. Spending may be heavily skewed, so show the raw distribution and, if useful, a clearly labelled log-scale view rather than hiding outliers.
4. Interpret the result in plain English and state whether it changes the business decision or only describes the data.
5. Export the final charts to `reports/figures/`; the notebook must run from top to bottom and regenerate them.
6. Do not manufacture findings to fit an expected story. If a chart reveals little or contradicts a hypothesis, state that honestly.

### Minimum visualization set, conditional on fields being available

| Figure | Question it answers | Example form | Business relevance |
|---|---|---|---|
| Dataset and time coverage | Which dates and records are represented? | Timeline + count summary | Stops claims that exceed the observed period |
| Purchase/spend distribution | Is spending concentrated among a small group? | Histogram/boxplot, with scale explained | Supports customer value analysis |
| Basket-value distribution | What does a typical transaction look like, and how skewed is it? | Histogram/boxplot | Gives context for basket-size rules |
| Purchase frequency distribution | How often do customers shop in the observed period? | Histogram/bar distribution | Helps define cadence groups |
| Recency vs. frequency or spend | Are recently active customers different from less-recent ones? | Scatter/hexbin or binned plot | Identifies groups for further investigation |
| Category/basket composition | Which categories meaningfully contribute to baskets or lines? | Sorted bars or stacked bars | Supports relevant assortment communication |
| Customer-level value distribution | How concentrated is total observed spend? | Quantiles/deciles and Lorenz-style view if useful | Clarifies concentration and targeting trade-offs |
| Campaign outcome by treatment | What raw response differences appear across groups? | Rate plot with sample sizes and uncertainty | Motivates campaign evaluation; not proof of causality by itself |

We will not force a figure if the relevant field is absent or the figure does not answer a useful question. We will add other figures when EDA discovers important data behavior.

### Required outputs

- `notebooks/01_data_quality_and_eda.ipynb`
- `reports/figures/eda_*.png` (reviewed static exports)
- `reports/sql_results/eda_summary_tables.csv` or separate small CSVs with clear names
- `reports/analysis/EDA_FINDINGS.md` with at least 5 evidence-backed observations where the data reasonably supports them. Each finding must include the metric, relevant group/period, interpretation, caveat, and possible business implication.

### What the user should learn

For each important chart, be able to say: “This chart measures X, each row/group means Y, the main observed pattern is Z, and it matters to the business because …”

### Completion gate

The notebook executes successfully, charts are actually saved, key numeric summaries reconcile to SQL, and the findings explain both what the chart says and what it does *not* prove. **No EDA phase is complete with only code or empty figure placeholders.**

---

## Phase 8 — Translate analysis into business insights and CRM segments

### In simple words

EDA describes what we see. Business analysis asks why it matters and what a manager could do. Segmentation turns measured behavior into understandable customer groups, but a label only has value if it helps make a decision.

### What we will do

1. Create an insight register. Each candidate insight must have evidence, affected customers, business relevance, limitations, and a proposed next action.
2. Define simple baseline segments (for example, recency/frequency/value or other field-supported behavioural groups) before considering clustering.
3. If a rule threshold is used, explain the population and reason for the threshold; show segment sizes and overlap.
4. Compare rule-based groups with alternatives only if that comparison can improve interpretability or actionability. Don't use clustering solely to say that ML was used.
5. Separate a mutually exclusive primary segment from overlapping behavioral flags when that fits the decision.
6. Map each segment to a possible CRM action. State why it might be worth testing and what evidence would validate the action.
7. Test every rule boundary, missing-value branch, precedence case and fallback.
8. Avoid unsupported labels such as “discount-sensitive,” “loyal,” “churn-risk,” or “high-profit” unless those constructs are directly measured or defensibly modeled.

### Skills used

Descriptive analytics, customer segmentation, rules/thresholds, business recommendations, explainability.

### Required outputs

- `docs/CRM_SEGMENTATION_METHOD.md`
- `src/custoloom/segmentation.py` and tests if executable rules are justified
- `sql/04_segment_analysis.sql`
- `reports/sql_results/segment_distribution.csv`
- `reports/figures/segment_size_and_value.png`
- `reports/analysis/CRM_INSIGHTS.md`

### Completion gate

Each segment has a measurable definition, a visible customer count, a reason for existing, an action hypothesis and a limitation. No claim says that a segment-level intervention will work until campaign evaluation supports it.

---

## Phase 9 — Audit the campaign experiment before any uplift model

### In simple words

A treatment/control dataset may help estimate whether marketing caused extra responses, but only if it was built in a way that supports that conclusion. We must inspect the design before training models.

### What we will do

1. Read the original competition/dataset documentation and verify what the treatment and outcome columns mean.
2. Determine unit of assignment and analysis (customer, household or another unit).
3. Establish whether treatment assignment was randomized, how eligibility worked, when treatment occurred, and when the outcome was measured.
4. Check treatment counts and outcome rates and compare important pre-treatment characteristics. These checks are diagnostics; they do not independently prove randomization.
5. Examine sample selection, missing labels, exclusions, exposure records if available, and whether controls could receive similar promotions.
6. Build a time diagram: feature observation period → treatment assignment/contact → outcome window. No feature may use information that happened after treatment or outcome.
7. Decide whether a causal/uplift evaluation is justified. If not, state exactly what weaker descriptive/predictive question is supported and redesign the next phase.

### Skills used

Experiment design, data analysis, causal reasoning, leakage prevention, target semantics.

### Required outputs

- `docs/CAMPAIGN_EXPERIMENT_AUDIT.md`
- `reports/sql_results/treatment_outcome_counts.csv`
- `reports/sql_results/pre_treatment_balance.csv` where appropriate
- `reports/figures/treatment_outcome_diagnostics.png`
- A signed-off decision: causal/uplift analysis supported, supported with caveats, or not supported

### Completion gate

The treatment/outcome definition and timeline are documented with source evidence. If the design or labels are inadequate, no uplift claim will be made. Do not proceed simply because a model package is available.

---

## Phase 10 — Build and evaluate predictive/uplift models

### In simple words

A model is useful only if it improves a well-defined task on data it has not trained on. Predicting who tends to buy is different from estimating who buys *because of* a campaign. Custoloom must distinguish these questions.

### Model sequence

1. **Naive baseline:** simple reference policy such as random targeting or the historically supported standard campaign policy.
2. **Business-rule baseline:** transparent customer ranking/eligibility rule, only where its logic is defensible.
3. **Response propensity model (optional):** estimates purchase/response probability. It is useful as a comparator but does not estimate incremental campaign effect.
4. **Uplift candidates (only if Phase 9 supports causal evaluation):** begin with a simple valid comparator, then consider methods such as S-/T-learners or an appropriate uplift learner. Choose the method according to data size, design, and implementation quality.
5. **Model comparison:** use a fixed validation/holdout strategy, appropriate metrics, baseline comparisons and uncertainty. Do not repeatedly optimize against the final holdout.

### What we will check

- Train/validation/holdout split definition and reproducibility.
- Pre-treatment-only model features; exclude treatment/outcome columns from features.
- Class imbalance and appropriate model metrics.
- Confusion/precision/recall/ROC-AUC or calibration only for a standard classification task where suitable.
- For uplift: uplift/Qini/AUUC or another justified metric, uplift at top-k, and policy comparisons versus random/standard targeting. Explain what each metric means and its limitations.
- Performance stability, model complexity, error analysis, subgroup caveats and uncertainty.
- No “best model” claim without comparing against a meaningful baseline on the same held-out evidence.

### Required outputs

- `notebooks/03_model_evaluation.ipynb`
- `src/custoloom/models/` only for reusable model pipeline code
- `reports/model_evaluation/model_comparison.csv`
- `reports/model_evaluation/targeting_policy_comparison.csv`
- `reports/figures/model_performance_comparison.png`
- `reports/figures/uplift_curve.png` and Qini curve only if appropriate
- `docs/MODEL_CARD.md` explaining purpose, data, intended use, metrics, limits and non-use cases

### Completion gate

Model results reproduce from documented commands, the holdout design is sound, baselines are compared fairly, and causal terminology matches the experiment audit. If a more complex model fails to improve the decision, keep the simpler model.

---

## Phase 11 — Turn model results into an explicit campaign decision

### In simple words

The model does not end the project. A manager needs to choose an action under a limit, such as only contacting the top 10% or 20% of eligible customers. We need to show the trade-off and explain the recommendation.

### What we will do

1. Define the allowed decision: for example, target the top X% from a ranked eligible population. Use several realistic contact limits rather than one arbitrary cutoff.
2. Compare the chosen model-based policy against random targeting, a relevant simple business rule, and all/none policies where meaningful.
3. Estimate incremental responders only if the evaluation permits it. State confidence intervals/uncertainty where feasible.
4. Estimate incremental revenue or profit only if we have valid monetary outcomes/costs or clearly labelled scenario assumptions. Don't call a response count “profit.”
5. Build a recommendation table showing the selected policy, number eligible/targeted, expected or estimated incremental outcome, comparison baseline, limitations and next real-world test.
6. Add an abstention rule: when data quality, eligibility, sample size or model uncertainty is insufficient, recommend further testing instead of overconfident targeting.

### Skills used

Decision science, KPI design, SQL aggregation, model interpretation, sensitivity analysis and business communication.

### Required outputs

- `docs/DECISION_POLICY.md`
- `sql/05_campaign_policy_evaluation.sql`
- `reports/sql_results/campaign_policy_comparison.csv`
- `reports/analysis/CAMPAIGN_RECOMMENDATION.md`
- One decision diagram or table showing how the recommendation is generated

### Completion gate

A manager can see the options, trade-offs, evidence, and uncertainty. The recommendation is derived from saved, reproducible calculations, not hard-coded presentation numbers.

---

## Phase 12 — Conditional MiroFish pilot: should we keep it?

### In simple words

This is a controlled experiment to decide whether a multi-agent simulator adds any useful campaign-planning ideas. It is not another predictive model.

### Preparation

Do this phase only after the core data analysis and campaign decision are working. Before installing MiroFish, inspect the current official repository, supported runtimes, license, configuration requirements, and expected LLM/Zep costs. Save the exact release/commit used because the project can change. Never commit API keys.

### Pilot protocol

1. Choose one clearly defined campaign-communication question, such as comparing two drafts for a hypothetical loyalty-program announcement. Do not claim it predicts purchase response.
2. Make a short seed pack consisting of the business brief, verified aggregated findings, segment assumptions, and the two message drafts. Exclude individual-level customer data and private identifiers.
3. Write down what the simulator is being asked to explore, what output would be useful, and what would count as failure *before* running it.
4. Compare a generic-input scenario with a data-grounded scenario that uses the same question and comparable settings.
5. Repeat runs where feasible; record prompts, configuration, model/provider, software version, runtime and costs.
6. Review outputs with a rubric: novelty, actionability, traceability to inputs, consistency across runs, and whether the result changes a proposed message or real-world test.
7. Label each output as simulated. Keep it separate from observed campaign results and model predictions.
8. Decide whether to retain the experiment in the portfolio. If it has little incremental value, remove it from the core narrative.

### Required outputs if the pilot proceeds

- `docs/MiroFish_PILOT.md`
- `reports/mirofish/pilot_protocol.md`
- `reports/mirofish/run_log.csv`
- `reports/mirofish/scenario_comparison.md`
- A go/no-go conclusion with evidence and cost/effort summary

### Completion gate

The pilot either demonstrates a specific useful role or is explicitly rejected. Never describe MiroFish as “human-accurate,” as proof of campaign effectiveness, or as a source of causal uplift.

---

## Phase 13 — Build the Power BI decision dashboard

### In simple words

Power BI is where the results become easy for a business manager to explore. It should not be a collection of pretty cards disconnected from the actual calculations.

### Dashboard pages

**Page 1 — Executive decision overview**
- Data coverage and population definition.
- Selected campaign targeting policy and target share.
- Relevant measured/estimated outcome against a comparison baseline.
- Clear warning labels for estimated, assumed or simulated quantities.

**Page 2 — Customer behaviour**
- Customer value/frequency distributions and segment sizes.
- Segment composition, recency and basket metrics.
- Filters only where they are analytically meaningful.

**Page 3 — Campaign evaluation**
- Treatment/control counts and outcomes.
- Model-versus-baseline policy comparisons.
- Uplift curves or other valid evaluation results only if Phase 9/10 supports them.

**Page 4 — CRM action explorer**
- Segment definition, number of customers, proposed action, rationale and caveats.
- No unsupported labels or guaranteed intervention claims.

**Page 5 — Scenario lab (only if MiroFish is retained)**
- Short simulated scenario summary, hypotheses and risks, repeat-run stability, and an explicit “simulation—not observed results” label.

### What we will do

1. Prepare a small, documented BI mart or export that avoids exposing raw customer-level identifiers.
2. Define measures in one place and document formula/filters.
3. Build visuals only from validated tables and tested measures.
4. Compare every important Power BI total/rate with a named SQL query and saved reconciliation result.
5. Test filters, drill-through, blank/missing categories, percentages, sample sizes, labels and refresh instructions.
6. Capture screenshots for the portfolio and retain the actual PBIX locally; follow Git/LFS or external storage guidance for binary handling rather than blindly committing large binaries.

### Skills used

Data modeling for BI, DAX where necessary, visual storytelling, KPI communication, reconciliation and dashboard UX.

### Required outputs

- `powerbi/Custoloom.pbix` or a clearly documented storage location
- `docs/POWER_BI_GUIDE.md`
- `reports/figures/dashboard_*.png` screenshots
- `reports/sql_results/powerbi_reconciliation.csv`

### Completion gate

A reviewer can interact with the report and trace major values back to SQL. No graph is allowed to display a different definition from the documented metric without explanation.

---

## Phase 14 — Integrated quality, reproducibility, and limits

### In simple words

Now we test the whole chain, not just individual pieces. Someone else should be able to set the project up, run the documented steps, and verify the main outcomes without trusting our word.

### What we will do

- Run unit tests and isolated synthetic fixtures after code changes.
- Run integration tests only when explicitly intended and safe; no test should ingest the whole dataset or overwrite valuable tables unintentionally.
- Test fresh setup instructions on a clean environment or a clearly described clean-state checklist.
- Reconcile important counts and aggregates from ingestion through the dashboard.
- Re-run notebooks from top to bottom.
- Confirm that every figure, metric and conclusion comes from reproducible computation.
- Check for secrets, raw data, local absolute paths, personal identifiers, large binaries and stale temporary files before pushing.
- Document limitations: dataset age, source design, sample selection, missing variables, uncertainty, external validity and model assumptions.
- Record any unsuccessful model or MiroFish pilot result instead of hiding it.

### Required outputs

- Automated tests and a final test summary with actual command output
- `docs/REPRODUCIBILITY.md`
- `docs/LIMITATIONS.md`
- `reports/analysis/final_reconciliation.csv`
- Clean Git status and a focused commit history

### Completion gate

The pipeline and results are reproducible to a reasonable level, important metrics reconcile, no critical defect remains open, and each limitation is visible to a reviewer.

---

## Phase 15 — Portfolio presentation and resume proof

### In simple words

Only now do we make the project look polished. The README and resume must describe work that has actually been completed, not the plan we hoped to complete.

### What we will do

1. Write the README around the business problem, system diagram, dataset/source notes, method, key verified findings, dashboard screenshots and how to reproduce results.
2. Add a short end-to-end demo path: one business question, one EDA discovery, one evaluated campaign-policy decision, and the dashboard page where the decision is visible.
3. Explain technical choices in plain English: why DuckDB, why particular metrics, why baseline, why uplift is or isn't justified, and why MiroFish was retained or removed.
4. Add selected saved SQL results and chart screenshots so a reviewer can see evidence without running the full pipeline.
5. Create the model card and data dictionary only with final verified definitions/results.
6. Write resume bullets from actual measured outcomes: dataset scale verified from the files, model improvement verified on holdout, pipeline runtime measured, test coverage/result observed, or dashboard delivered. Do not use unsupported claims like “increased revenue” without a real observed evaluation.
7. Prepare likely interview questions, especially metric semantics, aggregation grain, leakage, baselines, treatment assignment, uplift versus propensity, and limitations.

### Required outputs

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/DATA_DICTIONARY.md`
- `docs/METRIC_DEFINITIONS.md`
- `docs/MODEL_CARD.md` if a model is retained
- Screenshots and a reproducible demo narrative
- Resume bullets based solely on verified outcomes

### Completion gate

The project can be understood in two minutes, examined in detail by a technical reviewer, reproduced with documented steps, and defended honestly in an interview.

---

# Mandatory deliverables and what “showing the skill” means

## SQL

SQL is considered demonstrated only when the project includes readable `.sql` files and actual executed results. Each query should have a comment stating the question it answers. Result CSVs should have a short companion explanation. A row count without a definition is not enough.

Example deliverable set:

- SQL script that counts rows and distinct keys.
- SQL script that calculates basket/customer metrics at the documented grain.
- SQL script that compares campaign outcome rates by treatment group.
- A saved result table for each major query.
- A reconciliation that compares key SQL totals with notebook and Power BI outputs.

## EDA and visualization

EDA is considered demonstrated only when the notebook runs and the exported figures exist. The notebook must discuss each figure in words. The final repo should not merely contain plotting code, blank notebooks, or screenshots from an unrelated sample.

For each plot, record:

- The question.
- The data/SQL result used.
- Sample size and filters.
- Axes and units.
- Main observed result.
- Interpretation and business relevance.
- Limitation or warning against overinterpretation.

## Machine Learning

ML is considered demonstrated only when there is a valid target, a justified split, a baseline, model evaluation on held-out data, and explanation of whether the model helps the decision. Training a model and printing accuracy is not enough.

## Business decision-making

A business recommendation must show:

- Who/what decision it concerns.
- Which evidence supports it.
- What alternatives were considered.
- What constraints and assumptions apply.
- What risk or uncertainty remains.
- What should be tested next.

## MiroFish

MiroFish is considered demonstrated only if the actual application is run (not merely the static demo), the inputs and configuration are recorded, the scenarios are compared against a baseline, and its unique contribution is assessed. If setup/cost is impractical or it provides no useful additional insight, do not force it into the project.

---

# Checkpoint template to use after every phase

Antigravity must return the following in a phase report:

1. **What I was asked to do:** repeat the approved scope in simple words.
2. **What I changed:** list every file created/edited/deleted and why.
3. **What I ran:** exact commands, environment and whether a command was skipped.
4. **Actual results:** pasted test summaries, query outputs, chart paths and model metrics; no paraphrased success claim without evidence.
5. **What the results mean:** a beginner-friendly explanation, including any assumptions.
6. **What failed or remains unknown:** errors, limitations and incomplete checks.
7. **Data safety:** confirm whether source tables, raw files and secrets were touched; show relevant reconciliation results.
8. **Git state:** commit SHA if created, working-tree status, and whether the change was pushed.
9. **Acceptance criteria:** pass/fail for each agreed criterion with evidence.
10. **What the user should understand before continuing:** a short explanation or three knowledge-check questions, with answers provided if requested.

The assistant then reviews the evidence and recommends approve/revise. The user decides whether the next phase may begin.

---

# Current status after the planned fresh reset

After the reset, treat all phases as **NOT STARTED** until freshly executed and evidenced, even if similar files or tables previously existed. This is intentional: the goal is not to preserve earlier claims but to create a clean, understandable, defensible project.

| Phase | Status | Must not be marked complete until |
|---|---|---|
| 0. Reset | Not started | Only the approved plan remains in the working tree; source data is safely backed up; Git state is verified |
| 1. Business brief | Not started | Primary decision, KPIs and constraints are approved |
| 2. Source verification | Not started | Sources, definitions and data limitations are documented |
| 3. Environment | Not started | Clean environment and temporary DB tests pass |
| 4. Ingestion | Not started | Actual file and loaded row counts reconcile |
| 5. Data quality | Not started | SQL quality results and dispositions are reviewed |
| 6. Customer marts | Not started | Grain, keys, totals, cutoff and leakage checks pass |
| 7. EDA | Not started | Notebook executed; real figures exported; findings reviewed |
| 8. CRM segments | Not started | Definitions, populations, actions and edge cases validated |
| 9. Experiment audit | Not started | Target/treatment design is understood and documented |
| 10. Models | Not started | Baselines and valid holdout results justify retained models |
| 11. Decision engine | Not started | Recommendation and policy trade-offs are evidenced |
| 12. MiroFish pilot | Conditional | Actual pilot adds or fails to add useful evidence; go/no-go documented |
| 13. Power BI | Not started | Dashboard values reconcile to SQL and pages support decisions |
| 14. Integrated QA | Not started | Clean reproducibility and final integrity checks pass |
| 15. Portfolio | Not started | Deliverables exist and all claims match evidence |

---

# Important references for the MiroFish decision

- Official MiroFish repository/overview: https://github.com/666ghj/MiroFish
- Official demo: https://666ghj.github.io/mirofish-demo/
- Official FAQ describing the static demo, setup and evidence boundaries: https://github.com/666ghj/MiroFish/issues/726
- License: https://github.com/666ghj/MiroFish/blob/main/LICENSE

The plan deliberately treats MiroFish as conditional. Its official FAQ says the static demo contains prepared scenarios and fixed responses, and that the actual tool's simulation results are hypotheses rather than empirical facts or causal evidence. This is why its use is gated behind a pilot and an explicit decision about whether it adds value to Custoloom.

---

# Final rule

**Do not ask “What prompt do I paste next?” Ask “What are we trying to learn or decide, what evidence will this task produce, and how will we know it worked?”**

We will move one approved phase at a time. The user must be able to explain the purpose of a phase before the next implementation phase begins. If results are inadequate, revise the plan at that point and document why; the plan is a disciplined route, not a promise to force unsuitable methods to work.
