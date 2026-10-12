-- DDL for X5 RetailHero staging tables in DuckDB

CREATE TABLE IF NOT EXISTS stg_clients (
    client_id VARCHAR PRIMARY KEY,
    first_issue_date TIMESTAMP,
    first_redeem_date TIMESTAMP,
    age INTEGER,
    gender VARCHAR,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stg_products (
    product_id VARCHAR PRIMARY KEY,
    level_1 VARCHAR,
    level_2 VARCHAR,
    level_3 VARCHAR,
    level_4 VARCHAR,
    segment_id DOUBLE,
    brand_id VARCHAR,
    vendor_id VARCHAR,
    netto DOUBLE,
    is_own_trademark SMALLINT,
    is_alcohol SMALLINT,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Note: No primary or unique key on stg_purchases until row grain is established.
-- Preserves 100% of source records without dropping duplicates.
CREATE TABLE IF NOT EXISTS stg_purchases (
    client_id VARCHAR,
    transaction_id VARCHAR,
    transaction_datetime TIMESTAMP,
    regular_points_received DOUBLE,
    express_points_received DOUBLE,
    regular_points_spent DOUBLE,
    express_points_spent DOUBLE,
    purchase_sum DOUBLE,
    store_id VARCHAR,
    product_id VARCHAR,
    product_quantity DOUBLE,
    trn_sum_from_iss DOUBLE,
    trn_sum_from_red DOUBLE,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stg_uplift_train (
    client_id VARCHAR PRIMARY KEY,
    treatment_flg SMALLINT,
    target SMALLINT,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stg_uplift_test (
    client_id VARCHAR PRIMARY KEY,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
