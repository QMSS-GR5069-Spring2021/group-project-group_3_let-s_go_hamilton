# Databricks notebook source
# MAGIC %md
# MAGIC 
# MAGIC ## RF_regression_driver_results Prediction Model_part_3
# MAGIC 
# MAGIC However, we are still unsatisfied with the result and try to figure out better models. In this case, we use Random Forest Regression model as alternative. For Regression model, we change the output from “finishposition” into “driverRacePoints”. The R^2 is pretty high (69%), yet, the new issue is that the regression does not directly provide the prediction accuracy. In this case, we need to manual calculate the accuracy. Manually, we consider drivers who have the predicted “driverRacePoints” around 18 (15, 16,17,18, and 19) as in the second place.Finally, the accuracy on predicting both 0 and 1 is 92%, but the accuracy on predicting 1 (the prediction second palce/ real second palce) is 50%. Thus, we believe this model is good enough for prediction.

# COMMAND ----------

#Loading required Functions and Packages
from pyspark.sql import Window
from pyspark.sql.functions import datediff, current_date, avg, col, round, upper, max, min, lit, sum, countDistinct, concat,when
import pyspark.sql.functions as psf
from pyspark.sql.types import IntegerType
import numpy as np
import matplotlib as mp
import pandas as pd
import numpy as np
from datetime import datetime
import seaborn as sns
import tempfile
from pyspark.sql.types import DoubleType

import matplotlib.pyplot as plt

from numpy import savetxt

dbutils.library.installPyPI("mlflow", "1.14.0")
import mlflow.sklearn
from sklearn.model_selection import train_test_split
from sklearn.datasets import load_diabetes

from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from pyspark.ml.feature import VectorAssembler,StandardScaler,StringIndexer
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

# COMMAND ----------

# MAGIC %md
# MAGIC Data Cleansing and Features selection

# COMMAND ----------

#Reading Drivers data
drivers = spark.read.csv('s3://columbia-gr5069-main/raw/drivers.csv', header=True, inferSchema=True)

#Reading Races data
races = spark.read.csv('s3://columbia-gr5069-main/raw/races.csv', header=True, inferSchema=True)

#Reading Constructors data
constructors = spark.read.csv('s3://columbia-gr5069-main/raw/constructors.csv', header=True, inferSchema=True)


# COMMAND ----------

#Reading Drivers Performance data prepared for modeling with features
driverRaceDF= spark.read.csv('s3://group3-gr5069/processed/driver_race_results_mod_feat.csv', header=True, inferSchema=True)
driverRaceDF = driverRaceDF.drop('_c0')

driverRaceDF = driverRaceDF.withColumn("finishPosition", when(driverRaceDF["finishPosition"] == 999, 20).otherwise(driverRaceDF["finishPosition"]))
driverRaceDF = driverRaceDF.withColumn("finishPositionRM1", when(driverRaceDF["finishPositionRM1"] == 999, 20).otherwise(driverRaceDF["finishPositionRM1"]))  
driverRaceDF = driverRaceDF.withColumn("finishPositionRM2", when(driverRaceDF["finishPositionRM2"] == 999, 20).otherwise(driverRaceDF["finishPositionRM2"]))  
driverRaceDF = driverRaceDF.withColumn("finishPositionRM3", when(driverRaceDF["finishPositionRM3"] == 999, 20).otherwise(driverRaceDF["finishPositionRM3"]))
#Line of code to check data quality when needed
#driverRaceDF.select('avg_raceDur').withColumn('isNull_c',psf.col('avg_raceDur').isNull()).where('isNull_c = True').count()

# COMMAND ----------

# Dropping the pitstops data since this data is only available post 2011 races
driverRaceDF = driverRaceDF.drop("totPitstopDur","avgPitstopDur","countPitstops","firstPitstopLap","raceDate","constSeasonPoints","resultId")

# COMMAND ----------

# Dropping similar columns to target variables
driverRaceDF = driverRaceDF.drop("positionOrder","finishPosition","drivSecPosCat","raceLaps","driverSeasonPoints","drivSecPos","drivSecPosRM3"," drivSecPosRM2","drivSecPosRM1")

# COMMAND ----------

#Splitting the data frame into Train and Test data based on the requirements of the Project
driverRaceTrainDF = driverRaceDF.filter(driverRaceDF.raceYear <= 2010)

#Test data according to the question
driverRaceTestDF = driverRaceDF.filter(driverRaceDF.raceYear > 2010)
driverRaceTestDF = driverRaceTestDF.filter(driverRaceTestDF.raceYear < 2018)

# COMMAND ----------

# Converting the Spark Dataframes into Pandas Dataframes
driverRaceTrainDF_ml =driverRaceTrainDF.select("*").toPandas()
driverRaceTestDF_ml =driverRaceTestDF.select("*").toPandas()

# COMMAND ----------

X_train = driverRaceTrainDF_ml.drop(['driverRacePoints'], axis=1)
X_test = driverRaceTestDF_ml.drop(['driverRacePoints'], axis=1)
y_train = driverRaceTrainDF_ml['driverRacePoints']
y_test = driverRaceTestDF_ml['driverRacePoints']

# COMMAND ----------

# MAGIC %md
# MAGIC Random Forest (Regression)

# COMMAND ----------

def rf_reg(run_name, params, X_train, X_test, y_train, y_test):
# With autolog() enabled, all model parameters, a model score, and the fitted model are automatically logged.  
  with mlflow.start_run(run_name=run_name):
  
    # Set the model parameters. 
    #n_estimators = 1000
    #max_depth = 5
    #max_features = 5

    # Create and train model.
    rf = RandomForestRegressor(**params)
    #rf = RandomForestRegressor(n_estimators = n_estimators, max_depth = max_depth, max_features = max_features)
    rf.fit(X_train, y_train)

    # Use the model to make predictions on the test dataset.
    predictions = rf.predict(X_test)

    # Create metrics
    mse = mean_squared_error(y_test, predictions)
    mae = mean_absolute_error(y_test, predictions)
    r2 = r2_score(y_test, predictions)
    print("  mse: {}".format(mse))
    print("  mae: {}".format(mae))
    print("  R2: {}".format(r2))

    # Log metrics
    mlflow.log_metric("mse", mse)
    mlflow.log_metric("mae", mae)  
    mlflow.log_metric("r2", r2) 

    # Create feature importance
    importance = pd.DataFrame(list(zip(X_train.columns, rf.feature_importances_)), 
                                columns=["Feature", "Importance"]
                                ).sort_values("Importance", ascending=False)

    # Log importances using a temporary file
    temp = tempfile.NamedTemporaryFile(prefix="feature-importance-", suffix=".csv")
    temp_name = temp.name
    try:
      importance.to_csv(temp_name, index=False)
      mlflow.log_artifact(temp_name, "feature-importance.csv")
    finally:
      temp.close() # Delete the temp file

    # Create plot
    fig, ax = plt.subplots()

    sns.residplot(predictions, y_test, lowess=True)
    plt.xlabel("Predicted Driver Position")
    plt.ylabel("Residual")
    plt.title("Residual Plot")

    # Log residuals using a temporary file
    temp = tempfile.NamedTemporaryFile(prefix="residuals-", suffix=".png")
    temp_name = temp.name
    try:
      fig.savefig(temp_name)
      mlflow.log_artifact(temp_name, "residuals.png")
    finally:
      temp.close() # Delete the temp file

    display(fig)

# COMMAND ----------

params = {
  "n_estimators": 1000,
  "max_depth": 5,
  "random_state": 20}

rf_reg("Sixth Run", params, X_train, X_test, y_train, y_test)

# COMMAND ----------

# MAGIC %md
# MAGIC Data of the Best Model

# COMMAND ----------

 with mlflow.start_run():
  
    # Set the model parameters. 
    n_estimators = 1000
    max_depth = 5
    max_features = 10

    # Create and train model.
    rf = RandomForestRegressor(n_estimators = n_estimators, max_depth = max_depth, max_features = max_features)
    rf.fit(X_train, y_train)

    # Use the model to make predictions on the test dataset.
    predictions = rf.predict(X_test)

    # Create metrics
    mse = mean_squared_error(y_test, predictions)
    mae = mean_absolute_error(y_test, predictions)
    r2 = r2_score(y_test, predictions)
    print("  mse: {}".format(mse))
    print("  mae: {}".format(mae))
    print("  R2: {}".format(r2))

    # Log metrics
    mlflow.log_metric("mse", mse)
    mlflow.log_metric("mae", mae)  
    mlflow.log_metric("r2", r2) 

    # Create feature importance
    importance = pd.DataFrame(list(zip(X_train.columns, rf.feature_importances_)), 
                                columns=["Feature", "Importance"]
                                ).sort_values("Importance", ascending=False)

    # Log importances using a temporary file
    temp = tempfile.NamedTemporaryFile(prefix="feature-importance-", suffix=".csv")
    temp_name = temp.name
    try:
      importance.to_csv(temp_name, index=False)
      mlflow.log_artifact(temp_name, "feature-importance.csv")
    finally:
      temp.close() # Delete the temp file

    # Create plot
    fig, ax = plt.subplots()

    sns.residplot(predictions, y_test, lowess=True)
    plt.xlabel("Predicted Driver Position")
    plt.ylabel("Residual")
    plt.title("Residual Plot")

    # Log residuals using a temporary file
    temp = tempfile.NamedTemporaryFile(prefix="residuals-", suffix=".png")
    temp_name = temp.name
    try:
      fig.savefig(temp_name)
      mlflow.log_artifact(temp_name, "residuals.png")
    finally:
      temp.close() # Delete the temp file

    display(fig)

# COMMAND ----------

predictions = rf.predict(X_test)
driverRaceDFPred = X_test
driverRaceDFPred['predictions'] = pd.Series(predictions, index=driverRaceDFPred.index).round(0)
driverRaceDFPred['driverRacePoints'] = pd.Series(y_test, index=driverRaceDFPred.index)

# COMMAND ----------

print(predictions)

# COMMAND ----------

driverRaceDFPred=spark.createDataFrame(driverRaceDFPred) 

# COMMAND ----------

display(driverRaceDFPred)

# COMMAND ----------

driverRaceDFPred= driverRaceDFPred.join(drivers.select(col("driverId"), concat(drivers.forename,drivers.surname).alias("driverName"), col("nationality").alias("driverNat")), on=['driverId'],how="left").join(constructors.select(col("constructorId"),col("name").alias("constructorName"),col("nationality").alias("constructorNat")), on=['constructorId'], how="left").join(races.select(col("raceId"), col("name").alias("raceName"),col("round").alias("raceRound"), col("date").alias("raceDate")), on=['raceId'], how="left")

# COMMAND ----------

# MAGIC %md
# MAGIC Create the prediction result

# COMMAND ----------

# Creating a Binary column that says if a driver finished second or not
driverRaceDFPred = driverRaceDFPred.withColumn("drivSecPosPred", when((driverRaceDFPred.predictions >=15) & (driverRaceDFPred.predictions <= 19),1) .otherwise(0))

# Adding the real values if the driver position is second or not.
driverRaceDFPred = driverRaceDFPred.withColumn("drivSecPos", when(driverRaceDFPred.driverRacePoints == 18,1) .otherwise(0))


display(driverRaceDFPred)

# COMMAND ----------

# MAGIC %md
# MAGIC Save the dataframe

# COMMAND ----------

driverRaceDFPred.write.format('jdbc').options(
      url='jdbc:mysql://gc-gr5069.ccqalx6jsr2n.us-east-1.rds.amazonaws.com/gc2897_gr5069',
      driver='com.mysql.jdbc.Driver',
      dbtable='Final_Driver_Predit_Q2_G3',
      user='admin',
      password='12345678').mode('overwrite').save()

# COMMAND ----------

driverRaceDFPred_return = spark.read.format("jdbc").option("url", "jdbc:mysql://gc-gr5069.ccqalx6jsr2n.us-east-1.rds.amazonaws.com/gc2897_gr5069") \
    .option("driver", "com.mysql.jdbc.Driver").option("dbtable", "Final_Driver_Predit_Q2_G3") \
    .option("user", "admin").option("password", "12345678").load()

# COMMAND ----------

display(driverRaceDFPred_return)

# COMMAND ----------

# MAGIC %md
# MAGIC Prediction Power (Accuracy)

# COMMAND ----------

# MAGIC %md
# MAGIC Visualization is in the Superset

# COMMAND ----------

# MAGIC %md
# MAGIC We use Superset to show our prediction power(accuracy), the link is as below:
# MAGIC http://ec2-3-84-157-243.compute-1.amazonaws.com:8088/r/36
# MAGIC http://ec2-3-84-157-243.compute-1.amazonaws.com:8088/r/37

# COMMAND ----------

