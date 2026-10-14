# Airbnb Analytics Intelligence Platform

An end-to-end data engineering and analytics project built using **AWS, Snowflake, dbt, and Streamlit**.

## Project Overview

This project demonstrates how raw Airbnb booking and listing data can be transformed into structured, analytics-ready datasets and presented through an interactive dashboard.

The platform follows a layered data architecture and uses dbt for SQL transformations, data quality checks, reusable macros, incremental processing, and snapshots.

## Technology Stack

- **Cloud:** AWS
- **Data Warehouse:** Snowflake
- **Data Transformation:** dbt
- **Programming:** SQL and Python
- **Dashboard:** Streamlit
- **Visualization:** Plotly
- **Version Control:** Git and GitHub

## Architecture

AWS → Snowflake → dbt → Gold analytical models → Streamlit dashboard

- **Bronze layer:** Raw or initial data ingestion layer.
- **Silver layer:** Cleaned and transformed data.
- **Gold layer:** Business-ready analytical models.
- **Dashboard layer:** Interactive analytics and reporting.

*Adjust the ingestion details to match the exact AWS pipeline implemented in your repository.*

## Key Features

- Layered Bronze, Silver, and Gold data architecture.
- SQL transformations using dbt.
- Incremental models and snapshots.
- Reusable dbt macros and model testing.
- Snowflake key-pair authentication for the dashboard.
- Executive KPIs for bookings, revenue, average booking value, and listings.
- Interactive filters and Plotly visualizations.
- Data Explorer for inspecting analytical records.
- Data quality checks and Snowflake source validation.
- CSV export functionality.

## Dashboard

The Streamlit dashboard provides five main sections:

1. Executive Overview
2. Analytics
3. Interactive Analytics
4. Data Explorer
5. Data Catalog

## Data Model

The Gold layer includes analytical objects such as:

- `AIRBNB.GOLD.FACT`
- `AIRBNB.GOLD.OBT`
- `AIRBNB.GOLD.DIM_BOOKINGS`
- `AIRBNB.GOLD.DIM_HOSTS`
- `AIRBNB.GOLD.DIM_LISTINGS`

## Running the Dashboard

From the project root, install the project's dependencies using the existing environment and dependency configuration.


Start the dashboard:

```bash
uv run streamlit run streamlit_dashboard/app.py
```

## Data Security

- Credentials and private keys must not be committed to Git.
- Store secrets locally or in an appropriate secrets manager.
- Use the minimum Snowflake privileges needed for the application.

## Future Improvements

- Automated pipeline scheduling and monitoring.
- CI/CD for dbt model validation.
- Automated testing for dashboard calculations.
- Role-based access and deployment to a hosted platform.

## Author

Data engineering and analytics portfolio project demonstrating cloud data pipelines, warehouse transformations, and interactive business intelligence.
