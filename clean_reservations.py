
# clean_reservations.py

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, regexp_replace, upper, trim


def clean_reservations(df):
    """
    Limpia las reservas aplicando las reglas C1-C5.

    C1: Elimina espacios de route y convierte a mayúsculas.
    C2: Elimina espacios al inicio/final de status y convierte a mayúsculas.
    C3: Conserva únicamente CONFIRMED y CANCELLED.
    C4: Conserva precios no nulos y mayores que cero.
    C5: Elimina duplicados por reservation_id, conservando uno.
    """

    # C1: Normalizar la ruta
    df = df.withColumn(
        "route",
        upper(regexp_replace(col("route"), r"\s+", ""))
    )

    # C2: Normalizar el estado
    df = df.withColumn(
        "status",
        upper(trim(col("status")))
    )

    # C3: Filtrar estados permitidos
    df = df.filter(
        col("status").isin("CONFIRMED", "CANCELLED")
    )

    # C4: Filtrar precios válidos
    df = df.filter(
        col("price_cent").isNotNull() &
        (col("price_cent") > 0)
    )

    # C5: Eliminar duplicados por reservation_id
    df = df.dropDuplicates(["reservation_id"])

    return df


def main():
    spark = (
        SparkSession.builder
        .appName("CleanReservations")
        .getOrCreate()
    )

    # Leer reservas desde CSV.
    # Cambia la ruta por la ubicación real de tu archivo.
    df = (
        spark.read
        .option("header", True)
        .option("inferSchema", True)
        .csv("reservations.csv")
    )

    cleaned_df = clean_reservations(df)

    # Mostrar resultados
    cleaned_df.show(truncate=False)

    # Guardar resultados en CSV
    (
        cleaned_df.write
        .mode("overwrite")
        .option("header", True)
        .csv("output/cleaned_reservations")
    )

    spark.stop()


if __name__ == "__main__":
    main()
