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

-- Note: No primary or unique key on stg_purchases.
-- (transaction_id, product_id) is NOT unique across distinct baskets/stores.
-- source_row_number BIGINT is generated via WITH ORDINALITY from purchases.csv.gz
-- to preserve each source record's exact row identity and original file order.
CREATE TABLE IF NOT EXISTS stg_purchases (
    source_row_number BIGINT,
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

-- Canonical basket-level view:
-- Evaluates purchases at the true basket grain: (client_id, transaction_id).
-- purchase_sum and loyalty points are constant within each basket and are aggregated once (MAX)
-- to protect downstream queries from multiplying basket totals across line items.
CREATE OR REPLACE VIEW v_baskets AS
SELECT 
    client_id,
    transaction_id,
    MAX(transaction_datetime) AS transaction_datetime,
    MAX(store_id) AS store_id,
    MAX(purchase_sum) AS purchase_sum,
    MAX(regular_points_received) AS regular_points_received,
    MAX(regular_points_spent) AS regular_points_spent,
    COUNT(*) AS basket_line_count,
    ROUND(SUM(product_quantity), 2) AS basket_quantity,
    ROUND(SUM(trn_sum_from_iss), 2) AS basket_trn_sum_from_iss,
    ROUND(SUM(trn_sum_from_red), 2) AS basket_trn_sum_from_red
FROM stg_purchases
GROUP BY client_id, transaction_id;

