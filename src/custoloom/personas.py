"""Customer Personas and Rule-Based CRM Actions for Custoloom.

Transforms mart_customer_360 into an explainable, deterministic customer classification layer
(mart_customer_personas) that answers:
1. What observable shopping behavior best describes this customer? (primary_persona)
2. Which additional behavioral flags are relevant? (overlapping behavioral flags)
3. What reasonable CRM action could be considered, and what observed metrics support it?
   (recommended_action, action_rationale, action_qualification)

All thresholds are empirically derived from mart_customer_360 distributions and frozen.
"""

import argparse
from dataclasses import dataclass
import logging
from pathlib import Path
import sys
import time
from typing import Any, Optional
import duckdb

# Bootstrap package root for direct script execution
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from custoloom.config import DatabaseConfig, DatabaseConnectionError
from custoloom.db import DatabaseManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("custoloom.personas")

SOURCE_MART_TABLE = "mart_customer_360"
LOAD_PERSONAS_TABLE = "load_mart_customer_personas"
FINAL_PERSONAS_TABLE = "mart_customer_personas"

VALID_PRIMARY_PERSONAS = (
    "non_purchaser",
    "lapsed_shopper",
    "high_basket_value",
    "frequent_shopper",
    "category_focused",
    "infrequent_shopper",
    "steady_shopper",
)


@dataclass(frozen=True)
class PersonaThresholds:
    """Configurable numerical thresholds for customer personas and behavioral flags.

    All thresholds are empirically derived from mart_customer_360 as of the 2019-03-19 snapshot
    and frozen to ensure reproducible classifications across runs.
    """

    rule_version: str = "v1.0"

    # 1. High basket value cutoff (RUB)
    # Derived from: 75th percentile of avg_basket_value among purchasers (p75 = 609.19 RUB).
    # Frozen to 600.0 RUB.
    high_basket_value_rub: float = 600.0

    # 2. Frequent shopper visit cutoff (baskets in last 30d)
    # Derived from: 75th percentile of baskets_last_30d among active shoppers (p75 = 8.0 baskets).
    frequent_shopper_baskets_30d: int = 8

    # 3. Infrequent shopper visit cutoff (baskets in last 30d)
    # Derived from: 25th percentile of baskets_last_30d among active shoppers (p25 = 2.0 baskets).
    infrequent_shopper_max_baskets_30d: int = 2

    # 4. Category concentration share (Level-2 department line share)
    # Derived from: 90th percentile of favorite_level_2_line_share (p90 = 0.40).
    category_concentration_share: float = 0.40

    # 5. High historical spend cutoff (RUB)
    # Derived from: 75th percentile of total_spend (p75 = 11,101.92 RUB).
    # Frozen to 11,000.0 RUB.
    high_historical_spend_rub: float = 11000.0

    # 6. Broad category range cutoff (distinct Level-2 departments)
    # Derived from: 75th percentile of distinct_categories_level_2 (p75 = 15.0).
    broad_categories_count: int = 15

    # 7. Single store loyalty cutoff (share of baskets at favorite store)
    # Represents high physical location concentration (90%+ of visits).
    single_store_share: float = 0.90

    def __post_init__(self) -> None:
        """Validate that all thresholds are within reasonable analytical bounds."""
        if self.high_basket_value_rub <= 0:
            raise ValueError(f"high_basket_value_rub must be positive, got {self.high_basket_value_rub}")
        if self.frequent_shopper_baskets_30d <= 0:
            raise ValueError(f"frequent_shopper_baskets_30d must be positive, got {self.frequent_shopper_baskets_30d}")
        if self.infrequent_shopper_max_baskets_30d < 0:
            raise ValueError(f"infrequent_shopper_max_baskets_30d cannot be negative, got {self.infrequent_shopper_max_baskets_30d}")
        if self.infrequent_shopper_max_baskets_30d >= self.frequent_shopper_baskets_30d:
            raise ValueError(
                f"infrequent cutoff ({self.infrequent_shopper_max_baskets_30d}) must be less than "
                f"frequent cutoff ({self.frequent_shopper_baskets_30d})"
            )
        if not (0.0 <= self.category_concentration_share <= 1.0):
            raise ValueError(f"category_concentration_share must be in [0.0, 1.0], got {self.category_concentration_share}")
        if not (0.0 <= self.single_store_share <= 1.0):
            raise ValueError(f"single_store_share must be in [0.0, 1.0], got {self.single_store_share}")
        if not self.rule_version:
            raise ValueError("rule_version cannot be empty")


# Descriptive metadata recording the origin, population, and rationale of each threshold
THRESHOLD_METADATA: dict[str, dict[str, Any]] = {
    "high_basket_value_rub": {
        "cutoff": 600.0,
        "population": "Purchasers with total_baskets > 0 (400,162 customers)",
        "derivation": "75th percentile of avg_basket_value (p75 = 609.19 RUB)",
        "unit": "RUB",
        "description": "Distinguishes planned multi-item stock-up grocery trips from smaller fill-in trips.",
    },
    "frequent_shopper_baskets_30d": {
        "cutoff": 8,
        "population": "Active 30-day shoppers (400,162 customers)",
        "derivation": "75th percentile of baskets_last_30d (p75 = 8.0 baskets)",
        "unit": "baskets",
        "description": "Identifies habitual convenience shoppers visiting multiple times per week (mean 13.2 baskets).",
    },
    "infrequent_shopper_max_baskets_30d": {
        "cutoff": 2,
        "population": "Active 30-day shoppers (400,162 customers)",
        "derivation": "25th percentile of baskets_last_30d (p25 = 2.0 baskets)",
        "unit": "baskets",
        "description": "Identifies occasional or fill-in shoppers with only 1 to 2 visits in the 30-day window.",
    },
    "category_concentration_share": {
        "cutoff": 0.40,
        "population": "Active 30-day shoppers with categorized purchases",
        "derivation": "90th percentile of favorite_level_2_line_share (p90 = 0.40)",
        "unit": "line share ratio [0.0, 1.0]",
        "description": "Identifies shoppers with strong departmental focus (over 40% of item lines in one category).",
    },
    "high_historical_spend_rub": {
        "cutoff": 11000.0,
        "population": "Purchasers with total_baskets > 0",
        "derivation": "75th percentile of total_spend (p75 = 11,101.92 RUB)",
        "unit": "RUB",
        "description": "Identifies top quartile cumulative customer spend across observed tenure.",
    },
    "broad_categories_count": {
        "cutoff": 15,
        "population": "Purchasers with total_baskets > 0",
        "derivation": "75th percentile of distinct_categories_level_2 (p75 = 15.0)",
        "unit": "distinct categories",
        "description": "Identifies wide-basket shoppers who explore 15 or more distinct Level-2 departments.",
    },
    "single_store_share": {
        "cutoff": 0.90,
        "population": "Purchasers with total_baskets > 0",
        "derivation": "Business policy cutoff; 36.5% of population exhibits >= 90% single-store loyalty",
        "unit": "basket share ratio [0.0, 1.0]",
        "description": "Identifies shoppers who make 90%+ of their visits at a single primary store.",
    },
}


@dataclass(frozen=True)
class ActionPolicy:
    """Action recommendation and evidence-based rationale for a persona."""

    action: str
    rationale: str
    qualification: str


PERSONA_ACTIONS: dict[str, ActionPolicy] = {
    "non_purchaser": ActionPolicy(
        action="first_purchase_onboarding",
        rationale="Customer profile registered with zero recorded purchases. Test welcome communication and store directory to encourage initial visit.",
        qualification="Hypothesis only: assumes reachable contact channel; no observed purchase preferences exist for personalization.",
    ),
    "lapsed_shopper": ActionPolicy(
        action="reactivation_outreach",
        rationale="Customer has historical transactions but zero purchases in the past 30 days. Test gentle visit prompt or points balance reminder.",
        qualification="Hypothesis only: 30-day inactivity is descriptive recency, not a predictive churn score; causes of dormancy are unobserved.",
    ),
    "high_basket_value": ActionPolicy(
        action="large_basket_engagement",
        rationale="Observed average transaction spend is in the top quartile (>=600 RUB). Test communications acknowledging higher trip expenditure (e.g. basket-level milestones or stock-up reminders), without assuming unobserved premium preferences.",
        qualification="Hypothesis only: higher basket spend does not establish product quality preference, margin contribution, or price insensitivity.",
    ),
    "frequent_shopper": ActionPolicy(
        action="routine_replenishment_convenience",
        rationale="Observed visit frequency is in the top quartile (>=8 visits in past 30 days). Test convenience messaging (e.g. routine staple reminders, service hours, digital loyalty access) aligned with regular store visits.",
        qualification="Hypothesis only: high organic visit cadence means unsegmented financial incentives risk subsidizing transactions that would occur anyway.",
    ),
    "category_focused": ActionPolicy(
        action="category_specialist_discovery",
        rationale="Observed item lines are concentrated in a single Level-2 department (>=40% line share). Test relevant assortment updates within that observed department.",
        qualification="Hypothesis only: department concentration reflects past purchases, not full household demand; adjacent category receptivity requires testing.",
    ),
    "infrequent_shopper": ActionPolicy(
        action="cadence_stimulation_reminder",
        rationale="Observed visit frequency is 1 to 2 visits in the 30-day window. Test periodic visit prompts (e.g. weekly circular highlights) to encourage a return visit.",
        qualification="Hypothesis only: customer may split spend with competitor retailers; visit stimulation requires incremental uplift testing.",
    ),
    "steady_shopper": ActionPolicy(
        action="core_engagement_maintenance",
        rationale="Active customer with balanced visit cadence (3-7 visits in 30d) and typical basket spend (<600 RUB). Test standard circular communications and loyalty status updates.",
        qualification="Hypothesis only: operational baseline cohort representing median grocery shopping behavior.",
    ),
}


def clean_stale_persona_tables(con: duckdb.DuckDBPyConnection) -> None:
    """Clean up any stale load-stage persona tables from interrupted runs."""
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_name = ?;",
        [LOAD_PERSONAS_TABLE],
    ).fetchall()
    if rows:
        logger.warning("Found stale persona table '%s'. Dropping before build...", LOAD_PERSONAS_TABLE)
        con.execute(f"DROP TABLE IF EXISTS {LOAD_PERSONAS_TABLE};")


def generate_personas_sql(
    source_table: str = SOURCE_MART_TABLE,
    target_table: str = LOAD_PERSONAS_TABLE,
    thresholds: Optional[PersonaThresholds] = None,
    actions: Optional[dict[str, ActionPolicy]] = None,
) -> str:
    """Generate deterministic SQL to build the persona classification layer.

    Injects configured thresholds and action definitions dynamically so there is
    no duplicate specification of rules across Python and SQL.
    """
    t = thresholds or PersonaThresholds()
    a = actions or PERSONA_ACTIONS

    # Format action mapping expressions for SQL
    action_cases = "\n".join(
        f"            WHEN '{persona}' THEN '{policy.action}'"
        for persona, policy in a.items()
    )
    rationale_cases = "\n".join(
        f"            WHEN '{persona}' THEN '{policy.rationale}'"
        for persona, policy in a.items()
    )
    qualification_cases = "\n".join(
        f"            WHEN '{persona}' THEN '{policy.qualification}'"
        for persona, policy in a.items()
    )

    sql = f"""
    CREATE TABLE {target_table} AS
    WITH classified AS (
        SELECT 
            client_id,
            -- Deterministic Primary Persona (Strict Precedence)
            CASE
                -- 1. No purchase history (highest precedence)
                WHEN total_baskets = 0 OR first_purchase_datetime IS NULL 
                    THEN 'non_purchaser'
                -- 2. Previously active but lapsed in past 30 days
                WHEN baskets_last_30d = 0 
                    THEN 'lapsed_shopper'
                -- 3. High basket value (top quartile of avg_basket_value)
                WHEN avg_basket_value >= {t.high_basket_value_rub} 
                    THEN 'high_basket_value'
                -- 4. Frequent shopper (top quartile of monthly visit frequency)
                WHEN baskets_last_30d >= {t.frequent_shopper_baskets_30d} 
                    THEN 'frequent_shopper'
                -- 5. Category focused (top decile of departmental concentration)
                WHEN favorite_level_2_line_share >= {t.category_concentration_share} 
                    THEN 'category_focused'
                -- 6. Infrequent shopper (bottom quartile of active frequency: 1-2 visits)
                WHEN baskets_last_30d <= {t.infrequent_shopper_max_baskets_30d} 
                    THEN 'infrequent_shopper'
                -- 7. Fallback for remaining active customers
                ELSE 'steady_shopper'
            END AS primary_persona,

            -- Explainable reason for primary persona assignment
            CASE
                WHEN total_baskets = 0 OR first_purchase_datetime IS NULL 
                    THEN 'No recorded purchase transactions'
                WHEN baskets_last_30d = 0 
                    THEN 'Has historical purchases but 0 baskets in past 30 days'
                WHEN avg_basket_value >= {t.high_basket_value_rub} 
                    THEN 'Average basket value >= {t.high_basket_value_rub:.1f} RUB'
                WHEN baskets_last_30d >= {t.frequent_shopper_baskets_30d} 
                    THEN 'Baskets in last 30d >= {t.frequent_shopper_baskets_30d}'
                WHEN favorite_level_2_line_share >= {t.category_concentration_share} 
                    THEN 'Top level-2 category line share >= {t.category_concentration_share:.2f}'
                WHEN baskets_last_30d <= {t.infrequent_shopper_max_baskets_30d} 
                    THEN 'Baskets in last 30d <= {t.infrequent_shopper_max_baskets_30d}'
                ELSE 'Active customer with balanced frequency and basket size (fallback)'
            END AS persona_reason,

            -- Independent Overlapping Behavioral Flags
            CASE WHEN total_baskets = 0 OR first_purchase_datetime IS NULL THEN 1::SMALLINT ELSE 0::SMALLINT END AS flag_non_purchaser,
            CASE WHEN baskets_last_30d > 0 THEN 1::SMALLINT ELSE 0::SMALLINT END AS flag_active_30d,
            CASE WHEN avg_basket_value >= {t.high_basket_value_rub} THEN 1::SMALLINT ELSE 0::SMALLINT END AS flag_high_basket_value,
            CASE WHEN baskets_last_30d >= {t.frequent_shopper_baskets_30d} THEN 1::SMALLINT ELSE 0::SMALLINT END AS flag_frequent_shopper,
            CASE WHEN total_spend >= {t.high_historical_spend_rub} THEN 1::SMALLINT ELSE 0::SMALLINT END AS flag_high_historical_spend,
            CASE WHEN favorite_level_2_line_share >= {t.category_concentration_share} THEN 1::SMALLINT ELSE 0::SMALLINT END AS flag_category_concentrated,
            CASE WHEN distinct_categories_level_2 >= {t.broad_categories_count} THEN 1::SMALLINT ELSE 0::SMALLINT END AS flag_broad_category_range,
            CASE WHEN favorite_store_basket_share >= {t.single_store_share} THEN 1::SMALLINT ELSE 0::SMALLINT END AS flag_single_store_shopper,
            CASE WHEN has_redeemed = 1 THEN 1::SMALLINT ELSE 0::SMALLINT END AS flag_points_redeemer,

            -- Metadata
            '{t.rule_version}' AS rule_version,
            feature_cutoff_date
        FROM {source_table}
    )
    SELECT
        client_id,
        primary_persona,
        persona_reason,
        -- CRM Action Recommendation mapping
        CASE primary_persona
{action_cases}
            ELSE 'core_engagement_maintenance'
        END AS recommended_action,
        CASE primary_persona
{rationale_cases}
            ELSE 'Core customer foundation; maintain engagement via regular circular updates.'
        END AS action_rationale,
        CASE primary_persona
{qualification_cases}
            ELSE 'Operational baseline cohort.'
        END AS action_qualification,
        -- Overlapping flags
        flag_non_purchaser,
        flag_active_30d,
        flag_high_basket_value,
        flag_frequent_shopper,
        flag_high_historical_spend,
        flag_category_concentrated,
        flag_broad_category_range,
        flag_single_store_shopper,
        flag_points_redeemer,
        rule_version,
        feature_cutoff_date,
        CURRENT_TIMESTAMP AS personas_created_at
    FROM classified;
    """
    return sql


def build_personas_stage(
    con: duckdb.DuckDBPyConnection,
    thresholds: Optional[PersonaThresholds] = None,
    source_table: str = SOURCE_MART_TABLE,
    target_table: str = LOAD_PERSONAS_TABLE,
) -> float:
    """Execute SQL transformations to materialize the load-stage persona table."""
    logger.info("Building customer personas stage table '%s' from '%s'...", target_table, source_table)
    t0 = time.time()
    sql = generate_personas_sql(
        source_table=source_table,
        target_table=target_table,
        thresholds=thresholds,
    )
    con.execute(sql)
    elapsed = round(time.time() - t0, 3)
    logger.info("Persona staging table '%s' built in %.3fs", target_table, elapsed)
    return elapsed


def validate_personas_stage(
    con: duckdb.DuckDBPyConnection,
    target_table: str = LOAD_PERSONAS_TABLE,
    source_table: str = SOURCE_MART_TABLE,
) -> dict[str, Any]:
    """Validate that the persona table satisfies all structural, uniqueness, and completeness rules.

    Raises:
        RuntimeError: If any validation rule fails.
    """
    logger.info("Validating persona table '%s' against source '%s'...", target_table, source_table)

    # 1. Row count comparison
    src_count = con.execute(f"SELECT COUNT(*) FROM {source_table};").fetchone()[0]
    tgt_count = con.execute(f"SELECT COUNT(*) FROM {target_table};").fetchone()[0]
    if src_count != tgt_count:
        raise RuntimeError(
            f"Row count mismatch: {target_table} has {tgt_count:,} rows, "
            f"expected {src_count:,} matching {source_table}."
        )

    # 2. Grain and uniqueness check: exactly 1 row per customer
    dist_clients = con.execute(f"SELECT COUNT(DISTINCT client_id) FROM {target_table};").fetchone()[0]
    if dist_clients != tgt_count:
        raise RuntimeError(
            f"Grain violation: {target_table} has {dist_clients:,} distinct client_ids for {tgt_count:,} rows."
        )

    # 3. Completeness checks: no NULLs in critical classification fields
    null_checks = con.execute(f"""
        SELECT 
            COUNT(CASE WHEN client_id IS NULL THEN 1 END) AS null_clients,
            COUNT(CASE WHEN primary_persona IS NULL THEN 1 END) AS null_personas,
            COUNT(CASE WHEN persona_reason IS NULL THEN 1 END) AS null_reasons,
            COUNT(CASE WHEN recommended_action IS NULL THEN 1 END) AS null_actions,
            COUNT(CASE WHEN action_rationale IS NULL THEN 1 END) AS null_rationales,
            COUNT(CASE WHEN rule_version IS NULL THEN 1 END) AS null_versions,
            COUNT(CASE WHEN feature_cutoff_date IS NULL THEN 1 END) AS null_cutoffs
        FROM {target_table};
    """).fetchone()

    null_field_names = [
        "client_id", "primary_persona", "persona_reason",
        "recommended_action", "action_rationale", "rule_version", "feature_cutoff_date"
    ]
    for field_name, null_count in zip(null_field_names, null_checks):
        if null_count > 0:
            raise RuntimeError(f"Null violation in {target_table}: {null_count} rows have NULL {field_name}.")

    # 4. Valid personas verification
    persona_counts = dict(
        con.execute(f"SELECT primary_persona, COUNT(*) FROM {target_table} GROUP BY 1 ORDER BY 2 DESC;").fetchall()
    )
    for p_label in persona_counts:
        if p_label not in VALID_PRIMARY_PERSONAS:
            raise RuntimeError(f"Unexpected persona label found: '{p_label}'")

    total_persona_sum = sum(persona_counts.values())
    if total_persona_sum != tgt_count:
        raise RuntimeError(
            f"Persona counts sum mismatch: sum={total_persona_sum:,}, expected={tgt_count:,}"
        )

    # 5. Overlapping flags value bounds check (must be strictly 0 or 1)
    flag_columns = [
        "flag_non_purchaser",
        "flag_active_30d",
        "flag_high_basket_value",
        "flag_frequent_shopper",
        "flag_high_historical_spend",
        "flag_category_concentrated",
        "flag_broad_category_range",
        "flag_single_store_shopper",
        "flag_points_redeemer",
    ]
    flag_case_exprs = ", ".join(
        f"COUNT(CASE WHEN {c} NOT IN (0, 1) OR {c} IS NULL THEN 1 END)" for c in flag_columns
    )
    invalid_flags = con.execute(f"SELECT {flag_case_exprs} FROM {target_table};").fetchone()
    for col_name, invalid_count in zip(flag_columns, invalid_flags):
        if invalid_count > 0:
            raise RuntimeError(f"Flag value violation: column '{col_name}' has {invalid_count} invalid values.")

    flag_counts = {}
    for col in flag_columns:
        cnt = con.execute(f"SELECT COUNT(*) FROM {target_table} WHERE {col} = 1;").fetchone()[0]
        flag_counts[col] = cnt

    logger.info("Validation passed successfully: %d customers classified without gaps or nulls.", tgt_count)
    return {
        "status": "VALID",
        "total_customers": tgt_count,
        "persona_counts": persona_counts,
        "flag_counts": flag_counts,
    }


def promote_personas(
    con: duckdb.DuckDBPyConnection,
    load_table: str = LOAD_PERSONAS_TABLE,
    final_table: str = FINAL_PERSONAS_TABLE,
) -> None:
    """Promote load-stage persona table to final production table atomically."""
    logger.info("Promoting '%s' to '%s'...", load_table, final_table)
    con.execute(f"DROP TABLE IF EXISTS {final_table};")
    con.execute(f"ALTER TABLE {load_table} RENAME TO {final_table};")
    logger.info("Successfully promoted '%s'.", final_table)


def run_customer_personas_pipeline(
    manager: DatabaseManager,
    thresholds: Optional[PersonaThresholds] = None,
    source_table: str = SOURCE_MART_TABLE,
    target_table: str = FINAL_PERSONAS_TABLE,
) -> dict[str, Any]:
    """Execute the end-to-end customer persona classification pipeline."""
    logger.info("Starting Customer Personas pipeline into '%s'...", target_table)
    t_start = time.time()

    with manager.get_connection(read_only=False) as conn:
        exists = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?;",
            [source_table],
        ).fetchone()[0] > 0
        if not exists:
            raise RuntimeError(
                f"Validation error: required source table '{source_table}' does not exist. "
                "Please ensure Customer 360 mart is built before running personas."
            )

        clean_stale_persona_tables(conn)
        build_time = build_personas_stage(
            conn,
            thresholds=thresholds,
            source_table=source_table,
            target_table=LOAD_PERSONAS_TABLE,
        )
        val_summary = validate_personas_stage(
            conn,
            target_table=LOAD_PERSONAS_TABLE,
            source_table=source_table,
        )
        promote_personas(
            conn,
            load_table=LOAD_PERSONAS_TABLE,
            final_table=target_table,
        )

    total_time = round(time.time() - t_start, 3)
    logger.info("Customer Personas pipeline finished successfully in %.3fs.", total_time)

    return {
        "target_table": target_table,
        "total_customers": val_summary["total_customers"],
        "build_time_seconds": build_time,
        "total_time_seconds": total_time,
        "persona_counts": val_summary["persona_counts"],
        "flag_counts": val_summary["flag_counts"],
    }


def parse_args(args: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse command line arguments for the customer personas CLI."""
    parser = argparse.ArgumentParser(
        description="Build customer personas and rule-based CRM actions from mart_customer_360."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Optional path to persistent DuckDB database file.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Optional path to .env file for configuration.",
    )
    parser.add_argument(
        "--source-table",
        type=str,
        default=SOURCE_MART_TABLE,
        help=f"Source feature mart table name (default: {SOURCE_MART_TABLE}).",
    )
    parser.add_argument(
        "--target-table",
        type=str,
        default=FINAL_PERSONAS_TABLE,
        help=f"Target persona table name (default: {FINAL_PERSONAS_TABLE}).",
    )
    return parser.parse_args(args)


def main() -> None:
    """CLI entry point for building customer personas."""
    parsed = parse_args()
    config = DatabaseConfig.from_env(env_file=parsed.env_file)
    if parsed.db_path:
        config = DatabaseConfig(
            db_path=parsed.db_path,
            threads=config.threads,
            memory_limit=config.memory_limit,
            temp_directory=config.temp_directory,
        )

    manager = DatabaseManager(config=config)
    try:
        summary = run_customer_personas_pipeline(
            manager=manager,
            source_table=parsed.source_table,
            target_table=parsed.target_table,
        )
        print("\n=== Customer Personas Pipeline Complete ===")
        print(f"Target Table:     {summary['target_table']}")
        print(f"Total Customers:  {summary['total_customers']:,}")
        print(f"Execution Time:   {summary['total_time_seconds']:.2f}s")
        print("\nPrimary Persona Distribution:")
        for persona, count in summary["persona_counts"].items():
            pct = count / summary["total_customers"] * 100
            print(f"  {persona:25s}: {count:8,d} ({pct:5.2f}%)")
        print("\nOverlapping Behavioral Flags:")
        for flag, count in summary["flag_counts"].items():
            pct = count / summary["total_customers"] * 100
            print(f"  {flag:28s}: {count:8,d} ({pct:5.2f}%)")
    except Exception as exc:
        logger.error("Failed to build customer personas: %s", exc)
        sys.exit(1)
    finally:
        manager.close()


if __name__ == "__main__":
    main()
