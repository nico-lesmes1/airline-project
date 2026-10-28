"""EMR entry point for the airline history batch.

Usage:
  spark-submit spark_job.py --raw s3://bucket/raw/ \
    --curated s3://bucket/curated/reservations_curated/ \
    --metrics s3://bucket/curated/route_month_metrics/
"""

import argparse

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    count,
    date_format,
    lit,
    regexp_replace,
    sum as sum_,
    to_date,
    trim,
    upper,
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, help="S3 prefix containing flights.csv and reservations.csv")
    parser.add_argument("--curated", required=True)
    parser.add_argument("--metrics", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    spark = SparkSession.builder.appName("AirlineClean").getOrCreate()
    try:
        raw = args.raw.rstrip("/")
        flights = (
            spark.read.option("header", "true").option("inferSchema", "true")
            .csv(f"{raw}/flights.csv")
            .select(
                col("flight_id").cast("string"),
                upper(regexp_replace(col("route"), r"\s+", "")).alias("route"),
                to_date(col("flight_date")).alias("flight_date"),
                col("capacity").cast("bigint").alias("capacity"),
            )
            .withColumn("month", date_format("flight_date", "yyyy-MM"))
        )
        reservations = (
            spark.read.option("header", "true").option("inferSchema", "true")
            .csv(f"{raw}/reservations.csv")
            .select(
                col("reservation_id").cast("string"),
                col("flight_id").cast("string"),
                col("fare_class").cast("string"),
                col("price_cents").cast("bigint"),
                upper(trim(col("status"))).alias("status"),
            )
            .filter(col("status").isin("CONFIRMED", "CANCELLED"))
            .filter(col("price_cents").isNotNull() & (col("price_cents") > 0))
            .dropDuplicates(["reservation_id"])
        )

        detail = reservations.join(
            flights.select("flight_id", "route", "month"), "flight_id", "inner"
        ).select(
            "reservation_id", "flight_id", "route", "fare_class",
            "price_cents", "status", "month",
        )
        detail.write.mode("overwrite").partitionBy("month").parquet(args.curated)

        capacity = flights.groupBy("route", "month").agg(
            sum_("capacity").cast("bigint").alias("seats_capacity")
        )
        grouped = detail.groupBy("route", "month").agg(
            sum_(col("price_cents") * (col("status") == lit("CONFIRMED")).cast("bigint"))
            .cast("bigint").alias("revenue_cents"),
            sum_((col("status") == lit("CONFIRMED")).cast("bigint"))
            .cast("bigint").alias("seats_sold"),
            count("*").cast("bigint").alias("bookings"),
            sum_((col("status") == lit("CANCELLED")).cast("bigint"))
            .cast("bigint").alias("cancellations"),
        )
        metrics = (
            capacity.join(grouped, ["route", "month"], "left")
            .fillna(0, subset=["revenue_cents", "seats_sold", "bookings", "cancellations"])
            .withColumn("occupancy", col("seats_sold") / col("seats_capacity"))
            .select(
                "route", "month", "seats_capacity", "seats_sold", "occupancy",
                "revenue_cents", "bookings", "cancellations",
            )
        )
        metrics.write.mode("overwrite").parquet(args.metrics)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
