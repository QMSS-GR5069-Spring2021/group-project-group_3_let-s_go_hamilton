# Databricks notebook source
# MAGIC %md
# MAGIC #### Constructor Championship Inference

# COMMAND ----------

dbutils.library.installPyPI("mlflow", "1.14.0")

# COMMAND ----------

from pyspark.sql.types import DoubleType
from pyspark.ml.feature import VectorAssembler, Normalizer, StandardScaler
from pyspark.sql import Window
from pyspark.sql.functions import lag, col, asc, min, max, when

# COMMAND ----------

df = spark.read.csv('s3://group3-gr5069/interim/constructor_features.csv', header = True, inferSchema = True)

# COMMAND ----------

display(df)

# COMMAND ----------

cols_to_normalize = ['avg_fastestspeed', 
                     'avg_fastestlap',
                     'race_count',
                     'engineproblem',
                     'avgpoints_c',  
                     'unique_drivers',
                     'position',
                     'lag1_avg',
                     'lag2_avg', 
                     'lag1_pst',
                     'lag2_pst']

# COMMAND ----------

w = Window.partitionBy('year')
for c in cols_to_normalize:
    df = (df.withColumn('mini', min(c).over(w))
        .withColumn('maxi', max(c).over(w))
        .withColumn(c,  
                    when(col('maxi') == col('mini'), 0)
                    .otherwise(((col(c) - col('mini')) / (col('maxi') - col('mini')))))
        .drop('mini')
        .drop('maxi'))

# COMMAND ----------

feature_list =[ 'race_count','lag1_avg']

# COMMAND ----------

df = df.na.fill(value=0,subset=feature_list)

# COMMAND ----------

vecAssembler = VectorAssembler(inputCols = feature_list, outputCol = "features")

vecDF = vecAssembler.transform(df)

# COMMAND ----------

# MAGIC %md 
# MAGIC #### Logistic Regression

# COMMAND ----------

import os
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import mlflow.sklearn
import seaborn as sns
import tempfile
from pyspark.ml.classification import LogisticRegression
from pyspark.ml.evaluation import BinaryClassificationEvaluator
from pyspark.ml.tuning import CrossValidator, ParamGridBuilder

# COMMAND ----------

(trainDF, testDF) = vecDF.randomSplit([.8, .2], seed=42)

# COMMAND ----------

mlflow.sklearn.autolog()
# With autolog() enabled, all model parameters, a model score, and the fitted model are automatically logged.  

with mlflow.start_run():
  # logistic regression
  lr = LogisticRegression(featuresCol ='features', labelCol = "champion")

  # lasso
  # lr = LogisticRegression(featuresCol ='features', labelCol = "champion", elasticNetParam = 1, regParam=0.01)
  
  #lrModel = lr.fit(vecDF)
  #predictions = lrModel.transform(vecDF)
  #evaluator= BinaryClassificationEvaluator(labelCol='champion')
  
  # cross-validation
  paramGrid = ParamGridBuilder().build() # no parameter selection
  evaluator = BinaryClassificationEvaluator(labelCol="champion", metricName= "areaUnderROC")
  crossval = CrossValidator(estimator=lr, evaluator = evaluator, estimatorParamMaps = paramGrid, numFolds=5)
  modelCV = crossval.fit(vecDF)
  chk = modelCV.avgMetrics
  predictions = modelCV.transform(vecDF)
  
  # Log model
  mlflow.spark.log_model(modelCV, "5-fold-cross-validated-logistic-regression-with-selected-features")
  bestModel = modelCV.bestModel
  trainingSummary = bestModel.summary
  
  # Log parameters
  # mlflow.log_param("penalty", 0.01)
  
  # Create metrics
  #objectiveHistory = trainingSummary.objectiveHistory
  accuracy = trainingSummary.accuracy
  precision = trainingSummary.weightedPrecision
  recall = trainingSummary.weightedRecall
  
  falsePositiveRate = trainingSummary.weightedFalsePositiveRate
  truePositiveRate = trainingSummary.weightedTruePositiveRate
  
  fMeasure = trainingSummary.weightedFMeasure()
  areaUnderROC = trainingSummary.areaUnderROC
  testAreaUnderROC = evaluator.evaluate(predictions)
  
  # Log metrics
  mlflow.log_metric("falsePositiveRate", falsePositiveRate)
  mlflow.log_metric("truePositiveRate", truePositiveRate)
  mlflow.log_metric("fMeasure", fMeasure)
  mlflow.log_metric("precision", precision)
  mlflow.log_metric("recall", recall)
  mlflow.log_metric("areaUnderROC", areaUnderROC)

  # Feature Coefficients
  importance = pd.DataFrame(list(zip(feature_list, bestModel.coefficients)), 
                            columns=["Feature", "Importance"]
                          ).sort_values("Importance", ascending=False)
  
  # Log Coefficients using a temporary file
  temp = tempfile.NamedTemporaryFile(prefix="feature-importance-", suffix=".csv")
  temp_name = temp.name
  try:
    importance.to_csv(temp_name, index=False)
    mlflow.log_artifact(temp_name, "feature-importance.csv")
  finally:
    temp.close() 
  
  #Create ROC plot
  roc = trainingSummary.roc.toPandas()
  plt.plot(roc['FPR'],roc['TPR'])
  plt.ylabel('False Positive Rate')
  plt.xlabel('True Positive Rate')
  plt.title('ROC Curve')
  
  # Log ROC plot using a temporary file
  temp = tempfile.NamedTemporaryFile(prefix="ROC-Curve", suffix=".png")
  temp_name = temp.name
  try:
    plt.savefig(temp_name)
    mlflow.log_artifact(temp_name, "ROC-Curve.png")
  finally:
    temp.close() 
  plt.show()
  
  #Create Precision-Recall plot
  pr = trainingSummary.pr.toPandas()
  plt.plot(pr['recall'],pr['precision'])
  plt.ylabel('Precision')
  plt.xlabel('Recall')
  plt.title('Precision-Recall Curve')
  
  # Log Precision-Recall plot using a temporary file
  temp = tempfile.NamedTemporaryFile(prefix="Precision-Recall", suffix=".png")
  temp_name = temp.name
  try:
    plt.savefig(temp_name)
    mlflow.log_artifact(temp_name, "Precision-Recall.png")
  finally:
    temp.close() # Delete the temp file
  plt.show()
  print('Training set areaUnderROC: ' + str(trainingSummary.areaUnderROC))

# COMMAND ----------

predictions.columns

# COMMAND ----------

predDF_final = predictions.select('year',
 'constructorId',
 'avg_fastestspeed',
 'avg_fastestlap',
 'race_count',
 'engineproblem',
 'avgpoints_c',
 'participation',
 'gp_1',
 'gp_2',
 'gp_3',
 'gp_4',
 'gp_5',
 'gp_6',
 'gp_7',
 'gp_8',
 'gp_9',
 'gp_10',
 'gp_11',
 'gp_12',
 'gp_13',
 'gp_14',
 'gp_15',
 'gp_16',
 'gp_17',
 'gp_18',
 'gp_19',
 'gp_20',
 'gp_21',
 'gp_22',
 'gp_23',
 'gp_24',
 'gp_25',
 'gp_26',
 'gp_27',
 'gp_28',
 'gp_29',
 'gp_30',
 'gp_31',
 'gp_32',
 'gp_33',
 'gp_34',
 'gp_35',
 'gp_36',
 'gp_37',
 'gp_38',
 'gp_39',
 'gp_40',
 'gp_41',
 'gp_42',
 'gp_43',
 'gp_44',
 'gp_45',
 'gp_46',
 'gp_47',
 'gp_48',
 'gp_49',
 'gp_50',
 'gp_51',
 'gp_52',
 'gp_53',
 'gp_54',
 'gp_55',
 'gp_56',
 'gp_57',
 'gp_58',
 'gp_59',
 'gp_60',
 'gp_61',
 'gp_62',
 'gp_63',
 'gp_64',
 'gp_68',
 'gp_69',
 'gp_70',
 'gp_71',
 'gp_73',
 'unique_drivers',
 'position',
 'lag1_avg',
 'lag2_avg',
 'lag1_ptc',
 'lag2_ptc',
 'lag1_pst',
 'lag2_pst',
 'champion',
 'prediction')

# COMMAND ----------

predDF_final.write.format('jdbc').options(
      url='jdbc:mysql://sx2200-gr5069.ccqalx6jsr2n.us-east-1.rds.amazonaws.com/sx2200',
      driver='com.mysql.jdbc.Driver',
      dbtable='grp3_constructor_championship_inference',
      user='admin',
      password='Xs19980312!').mode('overwrite').save()

# COMMAND ----------



# COMMAND ----------

# MAGIC %md #### Read from db

# COMMAND ----------

predDF_final_done = spark.read.format("jdbc").option("url", "jdbc:mysql://sx2200-gr5069.ccqalx6jsr2n.us-east-1.rds.amazonaws.com/sx2200") \
    .option("driver", "com.mysql.jdbc.Driver").option("dbtable", "test_airbnb_preds") \
    .option("user", "admin").option("password", "Xs19980312!").load()

# COMMAND ----------

