import json
from sys import path as sys_path
from os import path as os_path
import psycopg2
from psycopg2 import sql, OperationalError

sys_path.append(os_path.realpath('../../'))
sys_path.append(os_path.realpath('../'))
sys_path.append(os_path.realpath('./'))

from utils.operation_utils import read_json
from utils.db_utils import DBUtil


TABLE_NAME = "PRODUCTS"
CREATE_TABLE_QUERY: str = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        PRODUCT_ID VARCHAR(255) PRIMARY KEY,
        MATERIAL_NAME VARCHAR(500),
        DESCRIPTION TEXT,
        UNIT_PRICE VARCHAR(50),
        UNIT VARCHAR(50),
        REGION VARCHAR(100),
        VENDOR VARCHAR(100),
        VAT_RATE VARCHAR(50),
        QUALITY_SCORE VARCHAR(50),
        SOURCE TEXT
    );
"""
INSERT_DATA_QUERY: str = f"""
    INSERT INTO {TABLE_NAME} (
        PRODUCT_ID, MATERIAL_NAME,
        DESCRIPTION, UNIT_PRICE,
        UNIT, REGION,
        VENDOR, VAT_RATE,
        QUALITY_SCORE, SOURCE
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (PRODUCT_ID) DO UPDATE SET
    MATERIAL_NAME = EXCLUDED.MATERIAL_NAME,
    DESCRIPTION = EXCLUDED.DESCRIPTION,
    UNIT_PRICE = EXCLUDED.UNIT_PRICE,
    UNIT = EXCLUDED.UNIT,
    REGION = EXCLUDED.REGION,
    VENDOR = EXCLUDED.VENDOR,
    VAT_RATE = EXCLUDED.VAT_RATE,
    QUALITY_SCORE = EXCLUDED.QUALITY_SCORE,
    SOURCE = EXCLUDED.SOURCE;
"""

def main() -> None:
    db_config_path = f"../configs/db_creds.json"
    db_config = read_json(path=db_config_path)
    print(f"(*) Config: {db_config}")

    data_path = "../../product_details_ingestion/data/castorama_materials.json"
    data = read_json(path=data_path)
    print(f"(*) Total {len(data)} data points found.")

    db_loader = DBUtil(db_config=db_config, table_name=TABLE_NAME)
    db_loader.init_queries(CREATE_TABLE_QUERY=CREATE_TABLE_QUERY, INSERT_DATA_QUERY=INSERT_DATA_QUERY)
    for row in data:
        values = (
            row["product_id"],
            row["material_name"],
            row["description"],
            row["unit_price"],
            row["unit"],
            row["region"],
            row["vendor"],
            row["vat_rate"],
            row["quality_score"],
            row["source"]
        )
        db_loader.execute_query(query=db_loader.INSERT_DATA_QUERY, params=values)
    print(f"✅ Database ingestion completed successfully into {db_config['dbname']}.{db_loader.TABLE_NAME}")
    # db_loader.preview_data(n=2)
    # db_loader.drop_table(mock=False)
    db_loader.close()

main()
