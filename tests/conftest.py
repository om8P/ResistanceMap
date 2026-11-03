"""Shared test setup. Tests need Spark, so they run inside the container."""
import glob
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
SPARK_HOME = os.environ.get("SPARK_HOME", "/opt/spark")
sys.path[:0] = [f"{SPARK_HOME}/python", *glob.glob(f"{SPARK_HOME}/python/lib/py4j-*.zip")]


@pytest.fixture(scope="session")
def spark():
    from pyspark.sql import SparkSession

    session = (SparkSession.builder.master("local[1]").appName("tests")
               .config("spark.sql.shuffle.partitions", "1").config("spark.ui.enabled", "false").getOrCreate())
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()
