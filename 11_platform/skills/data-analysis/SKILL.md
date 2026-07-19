---
name: data-analysis
description: Statistical analysis, trend detection, and insight generation from datasets
allowed_tools:
  - read_file
  - write_file
---

# Data Analysis Skill

You are now equipped to perform statistical analysis on datasets. Follow this methodology:

## Step 1: Understand the Data
- Identify column names and data types (numeric, categorical, datetime)
- Check for missing values and note their distribution
- Determine the granularity (per row = per what? per day? per customer?)

## Step 2: Descriptive Statistics
For numeric columns, compute:
- Count, mean, median, standard deviation
- Min/max and quartile range
- Identify outliers (values > 3 standard deviations from mean)

## Step 3: Trend Detection
- If timestamps present: identify upward/downward trends and inflection points
- If categorical: compute value frequencies and highlight dominant categories
- Correlate related columns where meaningful

## Step 4: Insights
- State the 3 most important findings in plain English
- Quantify each finding (not "revenue increased" but "revenue increased 23% from Q1 to Q2")
- Flag any anomalies or data quality concerns

## Output Format
- **Overview**: data shape and column summary
- **Statistics**: key metrics table
- **Trends**: narrative description with numbers
- **Insights**: top 3 findings, bulleted
- **Data Quality**: any gaps or anomalies noted
