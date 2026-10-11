-- DDL for X5 RetailHero staging tables in PostgreSQL

CREATE TABLE IF NOT EXISTS stg_clients (
    client_id VARCHAR(32) PRIMARY KEY,
    first_issue_date TIMESTAMP,
    first_redeem_date TIMESTAMP,
    age INTEGER,
    gender VARCHAR(1),
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stg_products (
    product_id VARCHAR(32) PRIMARY KEY,
    level_1 VARCHAR(32),
    level_2 VARCHAR(32),
    level_3 VARCHAR(32),
    level_4 VARCHAR(32),
    segment_id DOUBLE PRECISION,
    brand_id VARCHAR(32),
    vendor_id VARCHAR(32),
    netto DOUBLE PRECISION,
    is_own_trademark SMALLINT,
    is_alcohol SMALLINT,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stg_purchases (
    client_id VARCHAR(32),
    transaction_id VARCHAR(32),
    transaction_datetime TIMESTAMP,
    regular_points_received DOUBLE PRECISION,
    express_points_received DOUBLE PRECISION,
    regular_points_spent DOUBLE PRECISION,
    express_points_spent DOUBLE PRECISION,
    purchase_sum DOUBLE PRECISION,
    store_id VARCHAR(32),
    product_id VARCHAR(32),
    product_quantity DOUBLE PRECISION,
    trn_sum_from_iss DOUBLE PRECISION,
    trn_sum_from_red DOUBLE PRECISION,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stg_uplift_train (
    client_id VARCHAR(32) PRIMARY KEY,
    treatment_flg SMALLINT,
    target SMALLINT,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
