"""Registers a dataset's Parquet prefix as a Glue table so Athena can query it (AWS mode)."""
import re

import boto3

from app.config import settings
from app.engines import glue_db_name


def hive_type(t: str) -> str:
    u = t.upper()
    if u.startswith("DECIMAL"):
        return t.lower()
    return {
        "TINYINT": "tinyint", "SMALLINT": "smallint", "INTEGER": "int", "BIGINT": "bigint", "FLOAT": "float",
        "DOUBLE": "double", "BOOLEAN": "boolean", "DATE": "date", "VARCHAR": "string",
    }.get(re.split(r"[ (]", u)[0], "timestamp" if u.startswith("TIMESTAMP") else "string")


def register_table(org_id: str, ds_id: str, table_name: str, columns: list) -> None:
    glue = boto3.client("glue", region_name=settings.aws_region)
    db = glue_db_name(org_id)
    try:
        glue.create_database(DatabaseInput={"Name": db})
    except glue.exceptions.AlreadyExistsException:
        pass
    table = {
        "Name": table_name,
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {"classification": "parquet"},
        "StorageDescriptor": {
            "Columns": [{"Name": c["name"], "Type": hive_type(c["type"])} for c in columns],
            "Location": f"s3://{settings.s3_bucket}/org={org_id}/dataset={ds_id}/data/",
            "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
            "SerdeInfo": {"SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"},
        },
    }
    try:
        glue.create_table(DatabaseName=db, TableInput=table)
    except glue.exceptions.AlreadyExistsException:
        glue.update_table(DatabaseName=db, TableInput=table)


def drop_table(org_id: str, table_name: str) -> None:
    glue = boto3.client("glue", region_name=settings.aws_region)
    try:
        glue.delete_table(DatabaseName=glue_db_name(org_id), Name=table_name)
    except glue.exceptions.EntityNotFoundException:
        pass
