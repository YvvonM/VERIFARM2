"""Distributed Bronze→Silver cleaning with PySpark (for large historical backfills).

For multi-GB partner dumps, bypass single-node Python: read the raw Bronze data
directly from the object store (``s3a://…`` CSV/Parquet), clean and **enforce a
schema** in a distributed job, and write the structured Silver output (Parquet)
that the plain :mod:`app.bulk.processor` then ingests into the graph.

PySpark is heavy and deployment-specific (a Spark cluster / EMR / Glue), so it is
imported lazily and lives behind this seam — nothing in the API image depends on
it. Run on the cluster, not in the API container:

    spark-submit -m app.bulk.spark_job --input s3a://bucket/bronze/ --output s3a://bucket/silver/
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# The Silver contract the claim_bridge mapper expects downstream.
SILVER_COLUMNS = ["farmer_id", "land_size_hectares", "production_volume_kg", "observed_at"]


def run_bronze_to_silver(input_path: str, output_path: str, *, fmt: str = "csv") -> dict:
    """Read Bronze from object storage, clean + schema-enforce, write Silver Parquet.

    Returns a small summary (counts) for the audit trail. Imports pyspark lazily.
    """
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F
    from pyspark.sql.types import DoubleType, StringType, StructField, StructType, TimestampType

    spark = SparkSession.builder.appName("verifarms-bronze-to-silver").getOrCreate()
    try:
        reader = spark.read.option("header", True)
        raw = reader.csv(input_path) if fmt == "csv" else spark.read.parquet(input_path)
        total = raw.count()

        # Schema enforcement: coerce types, drop rows missing the key/identity.
        silver = (
            raw.select(
                F.col("farmer_id").cast(StringType()).alias("farmer_id"),
                F.col("land_size_hectares").cast(DoubleType()).alias("land_size_hectares"),
                F.col("production_volume_kg").cast(DoubleType()).alias("production_volume_kg"),
                F.to_timestamp(F.col("observed_at")).alias("observed_at"),
            )
            .where(F.col("farmer_id").isNotNull())
            .dropDuplicates(["farmer_id", "observed_at"])
        )
        kept = silver.count()
        silver.write.mode("overwrite").parquet(output_path)

        summary = {"input": input_path, "output": output_path, "total": total, "kept": kept, "dropped": total - kept}
        logger.info("Bronze→Silver: %s", summary)
        return summary
    finally:
        spark.stop()
