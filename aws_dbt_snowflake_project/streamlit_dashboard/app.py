import streamlit as st
import textwrap
import snowflake.connector
from cryptography.hazmat.primitives import serialization
import pandas as pd
import plotly.express as px
from plotly.subplots import make_subplots


def safe_divide(numerator, denominator, default=0.0):
    """Divide safely when values are missing, invalid, or zero."""
    try:
        if pd.isna(numerator) or pd.isna(denominator):
            return default
        denominator = float(denominator)
        numerator = float(numerator)
        if denominator == 0:
            return default
        result = numerator / denominator
        return result if pd.notna(result) else default
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        return default


def format_currency(value):
    """Format a numeric value as currency without raising on nulls."""
    try:
        if pd.isna(value):
            value = 0
        return f"${float(value):,.2f}"
    except (TypeError, ValueError, OverflowError):
        return "$0.00"


def show_empty_state(message="No data available for the selected filters."):
    """Display a consistent empty-results message."""
    st.info(f"ℹ️ {message}")


def run_data_quality_checks(df):
    """Run basic quality checks on the filtered booking data."""

    checks = []

    required_columns = [
        "BOOKING_ID",
        "BOOKING_DATE",
        "TOTAL_AMOUNT",
        "BOOKING_STATUS",
        "PROPERTY_TYPE",
    ]

    # Check required columns
    missing_columns = [
        column for column in required_columns
        if column not in df.columns
    ]

    checks.append({
        "Check": "Required columns",
        "Result": (
            "PASS" if not missing_columns else "FAIL"
        ),
        "Details": (
            "All required columns are available"
            if not missing_columns
            else f"Missing: {', '.join(missing_columns)}"
        ),
    })

    # Continue only when required columns exist
    if not missing_columns:
        duplicate_ids = df["BOOKING_ID"].duplicated().sum()

        checks.append({
            "Check": "Duplicate booking IDs",
            "Result": "PASS" if duplicate_ids == 0 else "WARNING",
            "Details": f"{duplicate_ids:,} duplicate IDs",
        })

        missing_amounts = df["TOTAL_AMOUNT"].isna().sum()

        checks.append({
            "Check": "Missing booking amounts",
            "Result": "PASS" if missing_amounts == 0 else "WARNING",
            "Details": f"{missing_amounts:,} missing amounts",
        })

        invalid_amounts = (
            pd.to_numeric(df["TOTAL_AMOUNT"], errors="coerce") < 0
        ).sum()

        checks.append({
            "Check": "Negative booking amounts",
            "Result": "PASS" if invalid_amounts == 0 else "WARNING",
            "Details": f"{invalid_amounts:,} negative amounts",
        })

        missing_dates = df["BOOKING_DATE"].isna().sum()

        checks.append({
            "Check": "Missing booking dates",
            "Result": "PASS" if missing_dates == 0 else "WARNING",
            "Details": f"{missing_dates:,} missing dates",
        })

    return pd.DataFrame(checks)


# ==========================================================
# PAGE CONFIGURATION
# ==========================================================

st.set_page_config(
    page_title="Airbnb Analytics Intelligence Platform",
    page_icon="📊",
    layout="wide"
)


# ==========================================================
# CUSTOM CSS
# ==========================================================

st.markdown(
    """
    <style>

    .main {
        padding-top: 1rem;
    }

    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }

    .subtitle {
        font-size: 1rem;
        color: #6b7280;
        margin-bottom: 1.5rem;
    }

    .section-header {
        font-size: 1.5rem;
        font-weight: 700;
        margin-top: 0.5rem;
        margin-bottom: 1rem;
    }

    .kpi-card {
        padding: 1.2rem;
        border-radius: 12px;
        border: 1px solid #e5e7eb;
        background: white;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        min-height: 120px;
    }

    .kpi-title {
        font-size: 0.85rem;
        font-weight: 600;
        color: #6b7280;
        text-transform: uppercase;
    }

    .kpi-value {
        font-size: 1.8rem;
        font-weight: 700;
        margin-top: 0.4rem;
    }

    .info-card {
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #e5e7eb;
        background: #fafafa;
        margin-bottom: 1rem;
    }

    section[data-testid="stSidebar"] {
        border-right: 1px solid #e5e7eb;
    }

    button[data-baseweb="tab"] {
        font-weight: 600;
    }

    div[data-testid="stDataFrame"] {
        border-radius: 10px;
    }

    .footer {
        text-align: center;
        color: #6b7280;
        font-size: 0.85rem;
        margin-top: 2rem;
        padding-top: 1rem;
        border-top: 1px solid #e5e7eb;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ==========================================================
# HEADER
# ==========================================================

st.markdown(
    """
    <div class="main-title">
        📊 Airbnb Analytics Intelligence Platform
    </div>

    <div class="subtitle">
        End-to-end data platform built with
        <b>AWS</b> → <b>Snowflake</b> → <b>dbt</b> → <b>Streamlit</b>
    </div>
    """,
    unsafe_allow_html=True
)



def validate_snowflake_source(conn):
    """Validate the Gold OBT table and required columns."""

    required_columns = {
        "BOOKING_ID",
        "BOOKING_DATE",
        "TOTAL_AMOUNT",
        "BOOKING_STATUS",
        "PROPERTY_TYPE",
        "LISTING_ID",
        "HOST_ID",
    }

    results = []

    # Check whether the OBT table is accessible
    try:
        table_check = conn.cursor()

        try:
            table_check.execute(
                "SELECT 1 FROM AIRBNB.GOLD.OBT LIMIT 1"
            )
            table_check.fetchone()

            results.append({
                "Check": "Gold OBT table access",
                "Status": "PASS",
                "Details": "AIRBNB.GOLD.OBT is accessible.",
            })

        finally:
            table_check.close()

    except Exception as exc:
        results.append({
            "Check": "Gold OBT table access",
            "Status": "FAIL",
            "Details": str(exc)[:300],
        })

        return pd.DataFrame(results)

    # Check whether required columns exist
    try:
        columns_check = conn.cursor()

        try:
            columns_check.execute("""
                SELECT COLUMN_NAME
                FROM AIRBNB.INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = 'GOLD'
                  AND TABLE_NAME = 'OBT'
            """)

            existing_columns = {
                row[0].upper()
                for row in columns_check.fetchall()
            }

        finally:
            columns_check.close()

        missing_columns = sorted(
            required_columns - existing_columns
        )

        results.append({
            "Check": "Required Gold OBT columns",
            "Status": "PASS" if not missing_columns else "FAIL",
            "Details": (
                "All required columns exist."
                if not missing_columns
                else "Missing: " + ", ".join(missing_columns)
            ),
        })

    except Exception as exc:
        results.append({
            "Check": "Required Gold OBT columns",
            "Status": "FAIL",
            "Details": str(exc)[:300],
        })

    return pd.DataFrame(results)


# ==========================================================
# SNOWFLAKE CONNECTION
# ==========================================================

@st.cache_resource
def get_snowflake_connection():

    config = st.secrets["snowflake"]

    private_key_path = config["private_key_path"]

    passphrase = config.get("private_key_passphrase")

    if passphrase:
        passphrase = passphrase.encode()

    with open(private_key_path, "rb") as key_file:

        private_key = serialization.load_pem_private_key(
            key_file.read(),
            password=passphrase
        )

    private_key_der = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    connection = snowflake.connector.connect(
        account=config["account"],
        user=config["user"],
        private_key=private_key_der,
        warehouse=config["warehouse"],
        database=config["database"],
        schema=config["schema"],
        role=config["role"]
    )

    return connection


@st.cache_data(ttl=300)
def run_query(_conn, query, params=None):

    return pd.read_sql(
        query,
        _conn,
        params=params
    )


# ==========================================================
# CONNECT TO SNOWFLAKE
# ==========================================================

try:

    conn = get_snowflake_connection()

except Exception as e:

    st.error(f"❌ Snowflake connection failed: {e}")
    st.stop()


# ==========================================================
# REFRESH DASHBOARD DATA
# ==========================================================

if st.sidebar.button(
    "🔄 Refresh Dashboard Data",
    use_container_width=True
):

    st.cache_data.clear()
    st.rerun()


# ==========================================================
# CONNECTION STATUS
# ==========================================================

st.success("🟢 Snowflake Connected")

st.info("🔵 Gold Layer: AIRBNB.GOLD.OBT")

st.success("🟢 dbt Transformation Layer Active")


# ==========================================================
# SIDEBAR FILTERS
# ==========================================================

st.sidebar.markdown(
    "### 🗄️ Dashboard Controls"
)

st.sidebar.markdown("---")


# ----------------------------------------------------------
# DATE RANGE
# ----------------------------------------------------------

date_query = """
    SELECT
        MIN(CAST(BOOKING_DATE AS DATE)) AS MIN_DATE,
        MAX(CAST(BOOKING_DATE AS DATE)) AS MAX_DATE
    FROM AIRBNB.GOLD.OBT
"""

date_df = run_query(
    conn,
    date_query
)


if date_df.empty or pd.isna(date_df.iloc[0]["MIN_DATE"]):

    st.error("No booking data available.")
    st.stop()


min_date = pd.to_datetime(
    date_df.iloc[0]["MIN_DATE"]
).date()

max_date = pd.to_datetime(
    date_df.iloc[0]["MAX_DATE"]
).date()


selected_dates = st.sidebar.date_input(
    "📅 Booking Date Range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)


if isinstance(selected_dates, (tuple, list)) and len(selected_dates) == 2:

    start_date = selected_dates[0]
    end_date = selected_dates[1]

else:

    start_date = min_date
    end_date = max_date


# ----------------------------------------------------------
# BOOKING STATUS
# ----------------------------------------------------------

status_query = """
    SELECT DISTINCT
        BOOKING_STATUS
    FROM AIRBNB.GOLD.OBT
    WHERE BOOKING_STATUS IS NOT NULL
    ORDER BY BOOKING_STATUS
"""

status_df = run_query(
    conn,
    status_query
)

status_options = status_df[
    "BOOKING_STATUS"
].dropna().tolist()


selected_status = st.sidebar.multiselect(
    "📌 Booking Status",
    options=status_options,
    default=status_options
)


if not selected_status:
    selected_status = status_options


# ----------------------------------------------------------
# PROPERTY TYPE
# ----------------------------------------------------------

property_filter_query = """
    SELECT DISTINCT
        PROPERTY_TYPE
    FROM AIRBNB.GOLD.OBT
    WHERE PROPERTY_TYPE IS NOT NULL
    ORDER BY PROPERTY_TYPE
"""

property_filter_df = run_query(
    conn,
    property_filter_query
)

property_options = property_filter_df[
    "PROPERTY_TYPE"
].dropna().tolist()


selected_property = st.sidebar.multiselect(
    "🏠 Property Type",
    options=property_options,
    default=property_options
)


if not selected_property:
    selected_property = property_options


# ==========================================================
# STEP 24 — ACTIVE FILTER SUMMARY
# ==========================================================

st.sidebar.markdown("---")

st.sidebar.markdown(
    "### 📌 Active Filters"
)

st.sidebar.write(
    f"📅 **Date:** {start_date} → {end_date}"
)

st.sidebar.write(
    f"📌 **Status:** {', '.join(map(str, selected_status))}"
)

st.sidebar.write(
    f"🏠 **Property:** {', '.join(map(str, selected_property))}"
)


# ==========================================================
# GLOBAL FILTER CLAUSE
# ==========================================================

status_placeholders = ",".join(
    ["%s"] * len(selected_status)
)

property_placeholders = ",".join(
    ["%s"] * len(selected_property)
)


filter_clause = f"""
    CAST(BOOKING_DATE AS DATE) BETWEEN %s AND %s
    AND BOOKING_STATUS IN ({status_placeholders})
    AND PROPERTY_TYPE IN ({property_placeholders})
"""


filter_params = [
    start_date,
    end_date,
    *selected_status,
    *selected_property
]


# ==========================================================
# TABS
# ==========================================================

(
    tab_overview,
    tab_analytics,
    tab_interactive,
    tab_explorer,
    tab_catalog
) = st.tabs(
    [
        "📊 Executive Overview",
        "📈 Analytics",
        "📊 Interactive Analytics",
        "🔍 Data Explorer",
        "🗄️ Data Catalog"
    ]
)


# ==========================================================
# TAB 1 — EXECUTIVE OVERVIEW
# ==========================================================

with tab_overview:

    st.markdown(
        '<div class="section-header">Executive Overview</div>',
        unsafe_allow_html=True
    )


    # ======================================================
    # CORE KPIs
    # ======================================================

    kpi_query = f"""
        SELECT
            COUNT(*) AS TOTAL_BOOKINGS,

            COALESCE(
                SUM(TOTAL_AMOUNT),
                0
            ) AS TOTAL_REVENUE,

            COALESCE(
                AVG(TOTAL_AMOUNT),
                0
            ) AS AVG_BOOKING_VALUE,

            COUNT(DISTINCT LISTING_ID) AS TOTAL_LISTINGS

        FROM AIRBNB.GOLD.OBT

        WHERE {filter_clause}
    """


    kpi_df = run_query(
        conn,
        kpi_query,
        filter_params
    )


    if kpi_df.empty:

        st.warning(
            "No records found for the selected filters."
        )

        st.stop()


    total_bookings = int(
        kpi_df.iloc[0]["TOTAL_BOOKINGS"]
    )

    total_revenue = float(
        kpi_df.iloc[0]["TOTAL_REVENUE"]
    )

    avg_booking_value = float(
        kpi_df.iloc[0]["AVG_BOOKING_VALUE"]
    )

    total_listings = int(
        kpi_df.iloc[0]["TOTAL_LISTINGS"]
    )


    col1, col2, col3, col4 = st.columns(4)


    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(
            textwrap.dedent(f"""
                <div class="kpi-card">
                    <div class="kpi-title">
                        TOTAL BOOKINGS
                    </div>
                    <div class="kpi-value">
                        {total_bookings:,}
                    </div>
                </div>
            """).strip(),
            unsafe_allow_html=True
        )

    with col2:
        st.markdown(
            textwrap.dedent(f"""
                <div class="kpi-card">
                    <div class="kpi-title">
                        TOTAL REVENUE
                    </div>
                    <div class="kpi-value">
                        ${total_revenue:,.2f}
                    </div>
                </div>
            """).strip(),
            unsafe_allow_html=True
        )

    with col3:
        st.markdown(
            textwrap.dedent(f"""
                <div class="kpi-card">
                    <div class="kpi-title">
                        AVG BOOKING VALUE
                    </div>
                    <div class="kpi-value">
                        ${avg_booking_value:,.2f}
                    </div>
                </div>
            """).strip(),
            unsafe_allow_html=True
        )

    with col4:
        st.markdown(
            textwrap.dedent(f"""
                <div class="kpi-card">
                    <div class="kpi-title">
                        TOTAL LISTINGS
                    </div>
                    <div class="kpi-value">
                        {total_listings:,}
                    </div>
                </div>
            """).strip(),
            unsafe_allow_html=True
        )

    st.markdown("")


    st.markdown("")


    # ======================================================
    # BOOKING TREND
    # ======================================================

    booking_trend_query = f"""
        SELECT
            CAST(BOOKING_DATE AS DATE) AS BOOKING_DATE,
            COUNT(*) AS TOTAL_BOOKINGS

        FROM AIRBNB.GOLD.OBT

        WHERE {filter_clause}

        GROUP BY CAST(BOOKING_DATE AS DATE)

        ORDER BY BOOKING_DATE
    """


    booking_trend_df = run_query(
        conn,
        booking_trend_query,
        filter_params
    )


    if not booking_trend_df.empty:

        fig_booking_trend = px.line(
            booking_trend_df,
            x="BOOKING_DATE",
            y="TOTAL_BOOKINGS",
            markers=True,
            title="Booking Trend"
        )

        fig_booking_trend.update_layout(
            template="plotly_white",
            xaxis_title="Booking Date",
            yaxis_title="Total Bookings",
            margin=dict(
                l=20,
                r=20,
                t=60,
                b=20
            )
        )

        st.plotly_chart(
            fig_booking_trend,
            use_container_width=True,
            key="overview_booking_trend"
        )


    # ======================================================
    # REVENUE TREND
    # ======================================================

    revenue_trend_query = f"""
        SELECT
            CAST(BOOKING_DATE AS DATE) AS BOOKING_DATE,

            COALESCE(
                SUM(TOTAL_AMOUNT),
                0
            ) AS TOTAL_REVENUE

        FROM AIRBNB.GOLD.OBT

        WHERE {filter_clause}

        GROUP BY CAST(BOOKING_DATE AS DATE)

        ORDER BY BOOKING_DATE
    """


    revenue_trend_df = run_query(
        conn,
        revenue_trend_query,
        filter_params
    )


    if not revenue_trend_df.empty:

        fig_revenue_trend = px.line(
            revenue_trend_df,
            x="BOOKING_DATE",
            y="TOTAL_REVENUE",
            markers=True,
            title="Revenue Trend"
        )

        fig_revenue_trend.update_layout(
            template="plotly_white",
            xaxis_title="Booking Date",
            yaxis_title="Total Revenue",
            margin=dict(
                l=20,
                r=20,
                t=60,
                b=20
            )
        )

        st.plotly_chart(
            fig_revenue_trend,
            use_container_width=True,
            key="overview_revenue_trend"
        )


    # ======================================================
    # BUSINESS PERFORMANCE METRICS
    # ======================================================

    st.subheader("Business Performance Metrics")


    performance_query = f"""
        SELECT

            COUNT(*) AS TOTAL_BOOKINGS,

            COALESCE(
                SUM(TOTAL_AMOUNT),
                0
            ) AS TOTAL_REVENUE,

            COUNT(
                DISTINCT LISTING_ID
            ) AS TOTAL_LISTINGS,

            COUNT_IF(
                UPPER(BOOKING_STATUS)
                IN ('CANCELLED', 'CANCELED')
            ) AS CANCELLED_BOOKINGS

        FROM AIRBNB.GOLD.OBT

        WHERE {filter_clause}
    """


    performance_df = run_query(
        conn,
        performance_query,
        filter_params
    )


    # Step 24: initialize safely
    cancellation_rate = 0
    revenue_per_booking = 0
    revenue_per_listing = 0


    if not performance_df.empty:

        performance_bookings = int(
            performance_df.iloc[0]["TOTAL_BOOKINGS"]
        )

        performance_revenue = float(
            performance_df.iloc[0]["TOTAL_REVENUE"]
        )

        performance_listings = int(
            performance_df.iloc[0]["TOTAL_LISTINGS"]
        )

        cancelled_bookings = int(
            performance_df.iloc[0]["CANCELLED_BOOKINGS"]
        )


        cancellation_rate = safe_divide(
            cancelled_bookings, performance_bookings
        ) * 100


        revenue_per_booking = safe_divide(
            performance_revenue, performance_bookings
        )


        revenue_per_listing = safe_divide(
            performance_revenue, performance_listings
        )


        col1, col2, col3 = st.columns(3)


        with col1:

            st.metric(
                "Cancellation Rate",
                f"{cancellation_rate:.2f}%"
            )


        with col2:

            st.metric(
                "Revenue per Booking",
                f"${revenue_per_booking:,.2f}"
            )


        with col3:

            st.metric(
                "Revenue per Listing",
                f"${revenue_per_listing:,.2f}"
            )


    # ======================================================
    # AUTOMATED BUSINESS INSIGHTS
    # ======================================================

    st.subheader("💡 Automated Business Insights")


    monthly_insight_query = f"""
        SELECT

            DATE_TRUNC(
                'MONTH',
                BOOKING_DATE
            ) AS PERIOD,

            COUNT(*) AS TOTAL_BOOKINGS,

            COALESCE(
                SUM(TOTAL_AMOUNT),
                0
            ) AS TOTAL_REVENUE

        FROM AIRBNB.GOLD.OBT

        WHERE {filter_clause}

        GROUP BY
            DATE_TRUNC(
                'MONTH',
                BOOKING_DATE
            )

        ORDER BY PERIOD
    """


    monthly_insight_df = run_query(
        conn,
        monthly_insight_query,
        filter_params
    )


    if not monthly_insight_df.empty:

        highest_booking_row = monthly_insight_df.loc[
            monthly_insight_df["TOTAL_BOOKINGS"].idxmax()
        ]

        highest_revenue_row = monthly_insight_df.loc[
            monthly_insight_df["TOTAL_REVENUE"].idxmax()
        ]


        st.write(
            f"📈 Highest booking volume was "
            f"**{int(highest_booking_row['TOTAL_BOOKINGS']):,} "
            f"bookings** in "
            f"**{pd.to_datetime(highest_booking_row['PERIOD']).strftime('%B %Y')}**."
        )


        st.write(
            f"💰 Highest revenue was "
            f"**${float(highest_revenue_row['TOTAL_REVENUE']):,.2f}** in "
            f"**{pd.to_datetime(highest_revenue_row['PERIOD']).strftime('%B %Y')}**."
        )


        if cancellation_rate > 20:

            st.warning(
                f"⚠️ Cancellation rate is "
                f"**{cancellation_rate:.2f}%**. "
                f"Consider investigating cancellation drivers."
            )

        else:

            st.success(
                f"✅ Cancellation rate is "
                f"**{cancellation_rate:.2f}%**."
            )


    # ======================================================
    # STEP 24 — EXECUTIVE BUSINESS SUMMARY
    # ======================================================

    st.subheader("🧠 Executive Business Summary")


    if total_bookings > 0:

        cancellation_message = (
            "Cancellation behavior should be investigated."
            if cancellation_rate > 20
            else "Cancellation behavior is within a manageable range."
        )


        st.info(
            f"📊 For the selected period, the platform recorded "
            f"**{total_bookings:,} bookings** generating "
            f"**${total_revenue:,.2f}** in revenue across "
            f"**{total_listings:,} listings**. "
            f"The average booking value was "
            f"**${avg_booking_value:,.2f}**, while the cancellation "
            f"rate was **{cancellation_rate:.2f}%**. "
            f"{cancellation_message}"
        )

    else:

        st.warning(
            "No business activity is available for the selected filters."
        )


    # ======================================================
    # STEP 24 — KPI INTERPRETATION
    # ======================================================

    st.markdown("### 📌 KPI Interpretation")


    interpretation_col1, interpretation_col2, interpretation_col3 = st.columns(3)


    with interpretation_col1:

        st.write(
            f"**💰 Revenue Efficiency**  \n"
            f"Each booking generated an average of "
            f"**${revenue_per_booking:,.2f}**."
        )


    with interpretation_col2:

        st.write(
            f"**🏠 Listing Efficiency**  \n"
            f"Average revenue per listing was "
            f"**${revenue_per_listing:,.2f}**."
        )


    with interpretation_col3:

        if cancellation_rate > 20:

            st.write(
                f"**⚠️ Cancellation Risk**  \n"
                f"Cancellation rate of **{cancellation_rate:.2f}%** "
                f"requires business attention."
            )

        else:

            st.write(
                f"**✅ Cancellation Risk**  \n"
                f"Cancellation rate of **{cancellation_rate:.2f}%** "
                f"is currently manageable."
            )


    # ======================================================
    # BOOKING DATA PREVIEW
    # ======================================================

    st.subheader("🔎 Booking Data Preview")


    preview_query = f"""
        SELECT *

        FROM AIRBNB.GOLD.OBT

        WHERE {filter_clause}

        ORDER BY BOOKING_DATE DESC

        LIMIT 10
    """


    preview_df = run_query(
        conn,
        preview_query,
        filter_params
    )


    st.dataframe(
        preview_df,
        use_container_width=True,
        hide_index=True
    )


    # ======================================================
    # STEP 24 — VALIDATION SNAPSHOT
    # ======================================================

    st.subheader("✅ Dashboard Validation Snapshot")


    validation_col1, validation_col2, validation_col3, validation_col4 = st.columns(4)


    with validation_col1:

        st.metric(
            "Filtered Records",
            f"{total_bookings:,}"
        )


    with validation_col2:

        st.metric(
            "Active Status Filters",
            f"{len(selected_status):,}"
        )


    with validation_col3:

        st.metric(
            "Active Property Filters",
            f"{len(selected_property):,}"
        )


    with validation_col4:

        st.metric(
            "Date Range Days",
            f"{(end_date - start_date).days + 1:,}"
        )


# ==========================================================
# TAB 2 — ANALYTICS
# ==========================================================

with tab_analytics:

    st.markdown(
        '<div class="section-header">📈 Analytics</div>',
        unsafe_allow_html=True
    )

    st.caption(
        "Detailed analysis of booking behavior, property performance, "
        "and top-performing listings and hosts."
    )


    # ======================================================
    # 1. BOOKING STATUS ANALYSIS
    # ======================================================

    st.subheader("📊 Booking Status Analysis")


    status_query = f"""
        SELECT

            BOOKING_STATUS,

            COUNT(*) AS TOTAL_BOOKINGS,

            COALESCE(
                SUM(TOTAL_AMOUNT),
                0
            ) AS TOTAL_REVENUE

        FROM AIRBNB.GOLD.OBT

        WHERE {filter_clause}

        GROUP BY BOOKING_STATUS

        ORDER BY TOTAL_BOOKINGS DESC
    """


    status_df = run_query(
        conn,
        status_query,
        filter_params
    )


    if not status_df.empty:

        col1, col2 = st.columns(2)


        with col1:

            fig_status_bookings = px.bar(
                status_df,
                x="BOOKING_STATUS",
                y="TOTAL_BOOKINGS",
                text_auto=True,
                title="Bookings by Status"
            )

            fig_status_bookings.update_layout(
                template="plotly_white",
                xaxis_title="Booking Status",
                yaxis_title="Total Bookings",
                margin=dict(
                    l=20,
                    r=20,
                    t=60,
                    b=20
                )
            )

            st.plotly_chart(
                fig_status_bookings,
                use_container_width=True,
                key="analytics_status_bookings"
            )


        with col2:

            fig_status_revenue = px.bar(
                status_df,
                x="BOOKING_STATUS",
                y="TOTAL_REVENUE",
                text_auto=".2s",
                title="Revenue by Booking Status"
            )

            fig_status_revenue.update_layout(
                template="plotly_white",
                xaxis_title="Booking Status",
                yaxis_title="Total Revenue",
                margin=dict(
                    l=20,
                    r=20,
                    t=60,
                    b=20
                )
            )

            st.plotly_chart(
                fig_status_revenue,
                use_container_width=True,
                key="analytics_status_revenue"
            )


    # ======================================================
    # 2. PROPERTY TYPE ANALYSIS
    # ======================================================

    st.subheader("🏠 Property Type Analysis")


    property_query = f"""
        SELECT

            PROPERTY_TYPE,

            COUNT(*) AS TOTAL_BOOKINGS,

            COALESCE(
                SUM(TOTAL_AMOUNT),
                0
            ) AS TOTAL_REVENUE,

            COALESCE(
                AVG(TOTAL_AMOUNT),
                0
            ) AS AVG_BOOKING_VALUE,

            COUNT(
                DISTINCT LISTING_ID
            ) AS TOTAL_LISTINGS

        FROM AIRBNB.GOLD.OBT

        WHERE {filter_clause}

        GROUP BY PROPERTY_TYPE

        ORDER BY TOTAL_REVENUE DESC
    """


    property_df = run_query(
        conn,
        property_query,
        filter_params
    )


    if not property_df.empty:

        col1, col2 = st.columns(2)


        with col1:

            fig_property_bookings = px.bar(
                property_df,
                x="PROPERTY_TYPE",
                y="TOTAL_BOOKINGS",
                text_auto=True,
                title="Bookings by Property Type"
            )

            fig_property_bookings.update_layout(
                template="plotly_white",
                xaxis_title="Property Type",
                yaxis_title="Total Bookings",
                margin=dict(
                    l=20,
                    r=20,
                    t=60,
                    b=20
                )
            )

            st.plotly_chart(
                fig_property_bookings,
                use_container_width=True,
                key="analytics_property_bookings"
            )


        with col2:

            fig_property_revenue = px.bar(
                property_df,
                x="PROPERTY_TYPE",
                y="TOTAL_REVENUE",
                text_auto=".2s",
                title="Revenue by Property Type"
            )

            fig_property_revenue.update_layout(
                template="plotly_white",
                xaxis_title="Property Type",
                yaxis_title="Total Revenue",
                margin=dict(
                    l=20,
                    r=20,
                    t=60,
                    b=20
                )
            )

            st.plotly_chart(
                fig_property_revenue,
                use_container_width=True,
                key="analytics_property_revenue"
            )


        st.markdown("### Property Performance")


        display_property_df = property_df.copy()


        display_property_df["TOTAL_REVENUE"] = (
            display_property_df["TOTAL_REVENUE"]
            .round(2)
        )


        display_property_df["AVG_BOOKING_VALUE"] = (
            display_property_df["AVG_BOOKING_VALUE"]
            .round(2)
        )


        display_property_df = display_property_df.rename(
            columns={
                "PROPERTY_TYPE": "Property Type",
                "TOTAL_BOOKINGS": "Bookings",
                "TOTAL_REVENUE": "Revenue",
                "AVG_BOOKING_VALUE": "Avg Booking Value",
                "TOTAL_LISTINGS": "Listings"
            }
        )


        st.dataframe(
            display_property_df,
            use_container_width=True,
            hide_index=True
        )


    # ======================================================
    # 3. TOP 5 LISTINGS
    # ======================================================

    st.subheader("🏆 Top 5 Listings by Revenue")


    top_listing_query = f"""
        SELECT

            LISTING_ID,

            COALESCE(
                SUM(TOTAL_AMOUNT),
                0
            ) AS TOTAL_REVENUE,

            COUNT(*) AS TOTAL_BOOKINGS

        FROM AIRBNB.GOLD.OBT

        WHERE {filter_clause}

        GROUP BY LISTING_ID

        ORDER BY TOTAL_REVENUE DESC

        LIMIT 5
    """


    top_listing_df = run_query(
        conn,
        top_listing_query,
        filter_params
    )


    if not top_listing_df.empty:

        fig_top_listings = px.bar(
            top_listing_df.sort_values(
                "TOTAL_REVENUE",
                ascending=True
            ),
            x="TOTAL_REVENUE",
            y="LISTING_ID",
            orientation="h",
            text_auto=".2s",
            title="Top 5 Listings by Revenue"
        )

        fig_top_listings.update_layout(
            template="plotly_white",
            xaxis_title="Total Revenue",
            yaxis_title="Listing ID",
            margin=dict(
                l=20,
                r=20,
                t=60,
                b=20
            )
        )

        st.plotly_chart(
            fig_top_listings,
            use_container_width=True,
            key="analytics_top_listings"
        )


    # ======================================================
    # 4. TOP 5 HOSTS
    # ======================================================

    st.subheader("👤 Top 5 Hosts by Revenue")


    top_host_query = f"""
        SELECT

            HOST_ID,

            MAX(HOST_NAME) AS HOST_NAME,

            COALESCE(
                SUM(TOTAL_AMOUNT),
                0
            ) AS TOTAL_REVENUE,

            COUNT(*) AS TOTAL_BOOKINGS

        FROM AIRBNB.GOLD.OBT

        WHERE {filter_clause}

        GROUP BY HOST_ID

        ORDER BY TOTAL_REVENUE DESC

        LIMIT 5
    """


    top_host_df = run_query(
        conn,
        top_host_query,
        filter_params
    )


    if not top_host_df.empty:

        top_host_df["HOST_LABEL"] = (
            top_host_df["HOST_NAME"]
            .fillna("Unknown Host")
            .astype(str)
            + " ("
            + top_host_df["HOST_ID"]
            .astype(str)
            + ")"
        )


        fig_top_hosts = px.bar(
            top_host_df.sort_values(
                "TOTAL_REVENUE",
                ascending=True
            ),
            x="TOTAL_REVENUE",
            y="HOST_LABEL",
            orientation="h",
            text_auto=".2s",
            title="Top 5 Hosts by Revenue"
        )

        fig_top_hosts.update_layout(
            template="plotly_white",
            xaxis_title="Total Revenue",
            yaxis_title="Host",
            margin=dict(
                l=20,
                r=20,
                t=60,
                b=20
            )
        )

        st.plotly_chart(
            fig_top_hosts,
            use_container_width=True,
            key="analytics_top_hosts"
        )


    # ======================================================
    # ANALYTICS SUMMARY
    # ======================================================

    st.subheader("📋 Analytics Summary")


    if not property_df.empty:

        best_property = property_df.iloc[0]["PROPERTY_TYPE"]

        best_property_revenue = float(
            property_df.iloc[0]["TOTAL_REVENUE"]
        )


        st.info(
            f"🏆 **Best Performing Property Type:** "
            f"{best_property} with "
            f"${best_property_revenue:,.2f} revenue."
        )


# ==========================================================
# TAB 3 — INTERACTIVE ANALYTICS
# ==========================================================

with tab_interactive:

    st.markdown(
        '<div class="section-header">📊 Interactive Analytics</div>',
        unsafe_allow_html=True
    )

    st.caption(
        "Explore booking and revenue performance using dynamic "
        "time aggregation and interactive business analytics."
    )


    # ======================================================
    # CONTROLS
    # ======================================================

    control_col1, control_col2 = st.columns(2)


    with control_col1:

        selected_metric = st.selectbox(
            "📌 Select Metric",
            [
                "Bookings",
                "Revenue"
            ]
        )


    with control_col2:

        selected_aggregation = st.selectbox(
            "📅 Aggregation",
            [
                "Monthly",
                "Weekly"
            ]
        )


    # ======================================================
    # PERIOD EXPRESSION
    # ======================================================

    if selected_aggregation == "Monthly":

        period_expression = """
            DATE_TRUNC(
                'MONTH',
                BOOKING_DATE
            )
        """

    else:

        period_expression = """
            DATE_TRUNC(
                'WEEK',
                BOOKING_DATE
            )
        """


    # ======================================================
    # INTERACTIVE DATA
    # ======================================================

    interactive_query = f"""
        SELECT

            {period_expression} AS PERIOD,

            COUNT(*) AS TOTAL_BOOKINGS,

            COALESCE(
                SUM(TOTAL_AMOUNT),
                0
            ) AS TOTAL_REVENUE

        FROM AIRBNB.GOLD.OBT

        WHERE {filter_clause}

        GROUP BY {period_expression}

        ORDER BY PERIOD
    """


    interactive_df = run_query(
        conn,
        interactive_query,
        filter_params
    )


    if not interactive_df.empty:

        # --------------------------------------------------
        # DYNAMIC TREND
        # --------------------------------------------------

        if selected_metric == "Bookings":

            y_column = "TOTAL_BOOKINGS"

            chart_title = (
                f"Booking Performance — "
                f"{selected_aggregation}"
            )

            y_title = "Total Bookings"

        else:

            y_column = "TOTAL_REVENUE"

            chart_title = (
                f"Revenue Performance — "
                f"{selected_aggregation}"
            )

            y_title = "Total Revenue"


        fig_interactive = px.line(
            interactive_df,
            x="PERIOD",
            y=y_column,
            markers=True,
            title=chart_title
        )


        fig_interactive.update_layout(
            template="plotly_white",
            hovermode="x unified",
            xaxis_title="Period",
            yaxis_title=y_title,
            margin=dict(
                l=20,
                r=20,
                t=60,
                b=20
            )
        )


        st.plotly_chart(
            fig_interactive,
            use_container_width=True,
            key="interactive_trend"
        )


        # --------------------------------------------------
        # STEP 23 — ENHANCED INTERACTIVE PERFORMANCE KPI
        # --------------------------------------------------

        total_interactive_bookings = int(
            interactive_df["TOTAL_BOOKINGS"].sum()
        )


        total_interactive_revenue = float(
            interactive_df["TOTAL_REVENUE"].sum()
        )


        first_period = interactive_df.iloc[0]

        latest_period = interactive_df.iloc[-1]


        first_bookings = float(
            first_period["TOTAL_BOOKINGS"]
        )

        latest_bookings = float(
            latest_period["TOTAL_BOOKINGS"]
        )


        first_revenue = float(
            first_period["TOTAL_REVENUE"]
        )

        latest_revenue = float(
            latest_period["TOTAL_REVENUE"]
        )


        booking_growth = safe_divide(
            latest_bookings - first_bookings, first_bookings
        ) * 100


        revenue_growth = safe_divide(
            latest_revenue - first_revenue, first_revenue
        ) * 100


        st.subheader(
            "📊 Interactive Performance KPI Summary"
        )


        kpi23_col1, kpi23_col2, kpi23_col3, kpi23_col4 = st.columns(4)


        with kpi23_col1:

            st.metric(
                "📦 Total Bookings",
                f"{total_interactive_bookings:,}",
                delta=f"{booking_growth:.2f}%"
            )


        with kpi23_col2:

            st.metric(
                "💰 Total Revenue",
                f"${total_interactive_revenue:,.2f}",
                delta=f"{revenue_growth:.2f}%"
            )


        with kpi23_col3:

            interactive_avg_booking_value = safe_divide(
                total_interactive_revenue, total_interactive_bookings
            )


            st.metric(
                "💵 Avg Booking Value",
                f"${interactive_avg_booking_value:,.2f}"
            )


        with kpi23_col4:

            st.metric(
                "📅 Periods",
                f"{len(interactive_df):,}"
            )


        # ==================================================
        # ADVANCED BUSINESS ANALYTICS
        # ==================================================

        st.subheader(
            "📊 Advanced Business Analytics"
        )


        advanced_col1, advanced_col2 = st.columns(2)


        with advanced_col1:

            st.metric(
                "Booking Growth",
                f"{booking_growth:.2f}%"
            )


        with advanced_col2:

            st.metric(
                "Revenue Growth",
                f"{revenue_growth:.2f}%"
            )


        # ==================================================
        # GROWTH ANALYSIS
        # ==================================================

        st.markdown("### 📈 Growth Analysis")


        growth_col1, growth_col2 = st.columns(2)


        with growth_col1:

            if booking_growth > 20:

                st.success(
                    f"🟢 Booking growth is strong "
                    f"at {booking_growth:.2f}%."
                )

            elif booking_growth < 0:

                st.error(
                    f"🔴 Booking growth is declining "
                    f"at {booking_growth:.2f}%."
                )

            else:

                st.info(
                    f"🟡 Booking growth is stable "
                    f"at {booking_growth:.2f}%."
                )


        with growth_col2:

            if revenue_growth > 20:

                st.success(
                    f"🟢 Revenue growth is strong "
                    f"at {revenue_growth:.2f}%."
                )

            elif revenue_growth < 0:

                st.error(
                    f"🔴 Revenue growth is declining "
                    f"at {revenue_growth:.2f}%."
                )

            else:

                st.info(
                    f"🟡 Revenue growth is stable "
                    f"at {revenue_growth:.2f}%."
                )


        # ==================================================
        # REVENUE & BOOKING PERFORMANCE
        # ==================================================

        st.subheader(
            "💰 Revenue & Booking Performance"
        )


        fig_revenue_booking = make_subplots(
            specs=[
                [{"secondary_y": True}]
            ]
        )


        fig_revenue_booking.add_scatter(
            x=interactive_df["PERIOD"],
            y=interactive_df["TOTAL_BOOKINGS"],
            mode="lines+markers",
            name="Bookings",
            secondary_y=False
        )


        fig_revenue_booking.add_scatter(
            x=interactive_df["PERIOD"],
            y=interactive_df["TOTAL_REVENUE"],
            mode="lines+markers",
            name="Revenue",
            secondary_y=True
        )


        fig_revenue_booking.update_layout(
            title="Revenue & Booking Performance",
            template="plotly_white",
            hovermode="x unified",
            margin=dict(
                l=20,
                r=20,
                t=60,
                b=20
            ),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )


        fig_revenue_booking.update_yaxes(
            title_text="Total Bookings",
            secondary_y=False
        )


        fig_revenue_booking.update_yaxes(
            title_text="Total Revenue",
            secondary_y=True
        )


        fig_revenue_booking.update_xaxes(
            title_text="Period"
        )


        st.plotly_chart(
            fig_revenue_booking,
            use_container_width=True,
            key="interactive_revenue_booking"
        )


        # ==================================================
        # PROPERTY PERFORMANCE
        # ==================================================

        st.subheader("🏠 Property Performance")


        interactive_property_query = f"""
            SELECT

                PROPERTY_TYPE,

                COUNT(*) AS TOTAL_BOOKINGS,

                COALESCE(
                    SUM(TOTAL_AMOUNT),
                    0
                ) AS TOTAL_REVENUE

            FROM AIRBNB.GOLD.OBT

            WHERE {filter_clause}

            GROUP BY PROPERTY_TYPE

            ORDER BY TOTAL_REVENUE DESC
        """


        interactive_property_df = run_query(
            conn,
            interactive_property_query,
            filter_params
        )


        if not interactive_property_df.empty:

            interactive_property_df[
                "REVENUE_PER_BOOKING"
            ] = interactive_property_df.apply(
                lambda row: safe_divide(
                    row["TOTAL_REVENUE"], row["TOTAL_BOOKINGS"]
                ),
                axis=1
            )


            property_col1, property_col2 = st.columns(2)


            with property_col1:

                fig_property_perf = px.bar(
                    interactive_property_df,
                    x="PROPERTY_TYPE",
                    y="TOTAL_REVENUE",
                    text_auto=".2s",
                    title="Revenue by Property Type"
                )


                fig_property_perf.update_layout(
                    template="plotly_white",
                    xaxis_title="Property Type",
                    yaxis_title="Total Revenue",
                    margin=dict(
                        l=20,
                        r=20,
                        t=60,
                        b=20
                    )
                )


                st.plotly_chart(
                    fig_property_perf,
                    use_container_width=True,
                    key="interactive_property_revenue"
                )


            with property_col2:

                fig_property_bookings = px.bar(
                    interactive_property_df,
                    x="PROPERTY_TYPE",
                    y="TOTAL_BOOKINGS",
                    text_auto=True,
                    title="Bookings by Property Type"
                )


                fig_property_bookings.update_layout(
                    template="plotly_white",
                    xaxis_title="Property Type",
                    yaxis_title="Total Bookings",
                    margin=dict(
                        l=20,
                        r=20,
                        t=60,
                        b=20
                    )
                )


                st.plotly_chart(
                    fig_property_bookings,
                    use_container_width=True,
                    key="interactive_property_bookings"
                )


        # ==================================================
        # REVENUE CONTRIBUTION
        # ==================================================

        st.subheader("💵 Revenue Contribution")


        contribution_query = f"""
            SELECT

                PROPERTY_TYPE,

                COALESCE(
                    SUM(TOTAL_AMOUNT),
                    0
                ) AS TOTAL_REVENUE

            FROM AIRBNB.GOLD.OBT

            WHERE {filter_clause}

            GROUP BY PROPERTY_TYPE

            ORDER BY TOTAL_REVENUE DESC
        """


        contribution_df = run_query(
            conn,
            contribution_query,
            filter_params
        )


        if not contribution_df.empty:

            fig_contribution = px.pie(
                contribution_df,
                names="PROPERTY_TYPE",
                values="TOTAL_REVENUE",
                hole=0.45,
                title="Revenue Contribution by Property Type"
            )


            fig_contribution.update_layout(
                template="plotly_white",
                margin=dict(
                    l=20,
                    r=20,
                    t=60,
                    b=20
                )
            )


            st.plotly_chart(
                fig_contribution,
                use_container_width=True,
                key="interactive_revenue_contribution"
            )


        # ==================================================
        # BEST PERFORMING PERIOD
        # ==================================================

        st.subheader("🏆 Best Performing Period")


        best_period = interactive_df.loc[
            interactive_df["TOTAL_REVENUE"].idxmax()
        ]


        best_period_col1, best_period_col2 = st.columns(2)


        with best_period_col1:

            st.metric(
                "Best Period",
                pd.to_datetime(
                    best_period["PERIOD"]
                ).strftime("%Y-%m-%d")
            )


        with best_period_col2:

            st.metric(
                "Revenue",
                f"${float(best_period['TOTAL_REVENUE']):,.2f}"
            )


        # ==================================================
        # PROPERTY BUSINESS RANKING
        # ==================================================

        st.subheader("🏅 Property Business Ranking")


        if not interactive_property_df.empty:

            ranking_df = interactive_property_df.copy()


            ranking_df = ranking_df.sort_values(
                "TOTAL_REVENUE",
                ascending=False
            )


            ranking_df["RANK"] = range(
                1,
                len(ranking_df) + 1
            )


            ranking_display = ranking_df[
                [
                    "RANK",
                    "PROPERTY_TYPE",
                    "TOTAL_BOOKINGS",
                    "TOTAL_REVENUE",
                    "REVENUE_PER_BOOKING"
                ]
            ].copy()


            ranking_display = ranking_display.rename(
                columns={
                    "RANK": "Rank",
                    "PROPERTY_TYPE": "Property Type",
                    "TOTAL_BOOKINGS": "Bookings",
                    "TOTAL_REVENUE": "Revenue",
                    "REVENUE_PER_BOOKING": "Revenue / Booking"
                }
            )


            st.dataframe(
                ranking_display,
                use_container_width=True,
                hide_index=True
            )


        # ==================================================
        # CANCELLATION ANALYSIS
        # ==================================================

        st.subheader("❌ Cancellation Analysis")


        cancellation_query = f"""
            SELECT

                COUNT(*) AS TOTAL_BOOKINGS,

                COUNT_IF(
                    UPPER(BOOKING_STATUS)
                    IN ('CANCELLED', 'CANCELED')
                ) AS CANCELLED_BOOKINGS

            FROM AIRBNB.GOLD.OBT

            WHERE {filter_clause}
        """


        cancellation_df = run_query(
            conn,
            cancellation_query,
            filter_params
        )


        # Step 24: initialize safely
        cancellation_rate_interactive = 0


        if not cancellation_df.empty:

            cancellation_total = int(
                cancellation_df.iloc[0]["TOTAL_BOOKINGS"]
            )

            cancellation_count = int(
                cancellation_df.iloc[0]["CANCELLED_BOOKINGS"]
            )


            cancellation_rate_interactive = safe_divide(
                cancellation_count, cancellation_total
            ) * 100


            st.metric(
                "Cancellation Rate",
                f"{cancellation_rate_interactive:.2f}%"
            )


            if cancellation_rate_interactive > 20:

                st.warning(
                    "⚠️ Cancellation rate is high. "
                    "Investigate cancellation drivers."
                )

            elif cancellation_rate_interactive > 10:

                st.info(
                    "🟡 Cancellation rate requires monitoring."
                )

            else:

                st.success(
                    "🟢 Cancellation rate is healthy."
                )


        # ==================================================
        # BUSINESS LEADERS
        # ==================================================

        st.subheader("👑 Business Leaders")


        leaders_query = f"""
            SELECT

                PROPERTY_TYPE,

                LISTING_ID,

                HOST_ID,

                HOST_NAME,

                TOTAL_AMOUNT

            FROM AIRBNB.GOLD.OBT

            WHERE {filter_clause}
        """


        leaders_df = run_query(
            conn,
            leaders_query,
            filter_params
        )


        if not leaders_df.empty:

            top_property = (
                leaders_df
                .groupby("PROPERTY_TYPE")["TOTAL_AMOUNT"]
                .sum()
                .idxmax()
            )


            top_listing = (
                leaders_df
                .groupby("LISTING_ID")["TOTAL_AMOUNT"]
                .sum()
                .idxmax()
            )


            top_host_row = (
                leaders_df
                .groupby(
                    ["HOST_ID", "HOST_NAME"],
                    dropna=False
                )["TOTAL_AMOUNT"]
                .sum()
                .sort_values(
                    ascending=False
                )
                .index[0]
            )


            leader_col1, leader_col2, leader_col3 = st.columns(3)


            with leader_col1:

                st.info(
                    f"🏠 **Top Property Type**\n\n"
                    f"{top_property}"
                )


            with leader_col2:

                st.info(
                    f"🏆 **Top Listing**\n\n"
                    f"{top_listing}"
                )


            with leader_col3:

                host_name = (
                    top_host_row[1]
                    if pd.notna(top_host_row[1])
                    else "Unknown Host"
                )


                st.info(
                    f"👤 **Top Host**\n\n"
                    f"{host_name}"
                )


        # ==================================================
        # AUTOMATED BUSINESS RECOMMENDATIONS
        # ==================================================

        st.subheader(
            "💡 Automated Business Recommendations"
        )


        if revenue_growth > 20:

            st.success(
                "🚀 Revenue is growing strongly. "
                "Consider increasing investment in high-performing "
                "properties and listings."
            )

        elif revenue_growth < 0:

            st.warning(
                "⚠️ Revenue is declining. "
                "Investigate underperforming properties and "
                "changes in booking behavior."
            )

        else:

            st.info(
                "📊 Revenue is relatively stable. "
                "Focus on optimizing high-value bookings."
            )


        if cancellation_rate_interactive > 20:

            st.warning(
                "❌ Cancellation rate is high. "
                "Investigate cancellation reasons and "
                "host/listing-level patterns."
            )


        if booking_growth > 20:

            st.success(
                "📈 Booking volume is growing strongly. "
                "Ensure sufficient listing capacity."
            )

        elif booking_growth < 0:

            st.warning(
                "📉 Booking volume is declining. "
                "Review demand and property performance."
            )


        # ==================================================
        # AGGREGATED DATA
        # ==================================================

        with st.expander(
            "🔎 View Aggregated Analytics Data"
        ):

            st.dataframe(
                interactive_df,
                use_container_width=True,
                hide_index=True
            )

    else:

        st.warning(
            "No interactive analytics data found "
            "for the selected filters."
        )


# ==========================================================
# TAB 4 — DATA EXPLORER
# ==========================================================

with tab_explorer:

    st.markdown(
        '<div class="section-header">🔍 Data Explorer</div>',
        unsafe_allow_html=True
    )

    st.caption(
        "Explore filtered records from the Gold OBT analytical table."
    )


    explorer_query = f"""
        SELECT *

        FROM AIRBNB.GOLD.OBT

        WHERE {filter_clause}

        ORDER BY BOOKING_DATE DESC

        LIMIT 1000
    """


    explorer_df = run_query(
        conn,
        explorer_query,
        filter_params
    )


    if not explorer_df.empty:

        search_text = st.text_input(
            "🔎 Search across all columns",
            placeholder="Enter a value to search..."
        )


        filtered_explorer_df = explorer_df.copy()


        if search_text:

            search_mask = (
                filtered_explorer_df
                .astype(str)
                .apply(
                    lambda column:
                    column.str.contains(
                        search_text,
                        case=False,
                        na=False
                    )
                )
                .any(axis=1)
            )


            filtered_explorer_df = (
                filtered_explorer_df[
                    search_mask
                ]
            )


        st.write(
            f"Showing **{len(filtered_explorer_df):,}** records"
        )


        st.dataframe(
            filtered_explorer_df,
            use_container_width=True,
            hide_index=True
        )


        csv_data = filtered_explorer_df.to_csv(
            index=False
        ).encode("utf-8")


        st.download_button(
            label="⬇️ Download Filtered Data",
            data=csv_data,
            file_name="airbnb_filtered_data.csv",
            mime="text/csv",
            use_container_width=True
        )

    else:

        show_empty_state(
            "No records match the selected filters. Try changing the date range, status, or property type."
        )


# ==========================================================
# TAB 5 — DATA CATALOG
# ==========================================================

with tab_catalog:

    st.markdown(
        '<div class="section-header">🗄️ Data Catalog</div>',
        unsafe_allow_html=True
    )

    st.caption(
        "Gold-layer tables and analytical schema information."
    )


    # ======================================================
    # GOLD TABLES
    # ======================================================

    st.subheader("📋 Gold Layer Tables")


    gold_tables_query = """
        SELECT
            TABLE_NAME,
            TABLE_TYPE
        FROM AIRBNB.INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = 'GOLD'
        ORDER BY TABLE_NAME
    """


    gold_tables_df = run_query(
        conn,
        gold_tables_query
    )


    if not gold_tables_df.empty:

        st.dataframe(
            gold_tables_df,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "No Gold layer tables found."
        )


    # ======================================================
    # OBT STRUCTURE
    # ======================================================

    st.subheader("🔎 OBT Table Structure")


    obt_columns_query = """
        SELECT

            ORDINAL_POSITION,

            COLUMN_NAME,

            DATA_TYPE

        FROM AIRBNB.INFORMATION_SCHEMA.COLUMNS

        WHERE TABLE_SCHEMA = 'GOLD'

        AND TABLE_NAME = 'OBT'

        ORDER BY ORDINAL_POSITION
    """


    obt_columns_df = run_query(
        conn,
        obt_columns_query
    )


    if not obt_columns_df.empty:

        st.dataframe(
            obt_columns_df,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "Unable to retrieve OBT column metadata."
        )


    # ======================================================
    # STEP 25.1 — DATA QUALITY CHECKS
    # ======================================================

    st.subheader("🧪 Data Quality Checks")

    quality_query = """
        SELECT
            BOOKING_ID,
            BOOKING_DATE,
            TOTAL_AMOUNT,
            BOOKING_STATUS,
            PROPERTY_TYPE
        FROM AIRBNB.GOLD.OBT
    """

    try:
        quality_source_df = run_query(conn, quality_query)

        if not quality_source_df.empty:
            quality_df = run_data_quality_checks(quality_source_df)

            st.dataframe(
                quality_df,
                use_container_width=True,
                hide_index=True
            )

            if (quality_df["Result"] == "FAIL").any():
                st.error("Some required data-quality checks failed.")
            elif (quality_df["Result"] == "WARNING").any():
                st.warning("Please review the data-quality warnings above.")
            else:
                st.success("All displayed data-quality checks passed.")
        else:
            show_empty_state("No booking records are available for quality checks.")

    except Exception as exc:
        st.error(f"Unable to run data-quality checks: {exc}")


    # ======================================================
    # STEP 25.2 — SNOWFLAKE SOURCE VALIDATION
    # ======================================================

    st.subheader("❄️ Snowflake Source Validation")

    if st.button(
        "🔍 Validate Snowflake Gold Source",
        key="validate_snowflake_gold_source"
    ):
        with st.spinner("Validating Snowflake source..."):

            source_validation_df = validate_snowflake_source(
                conn
            )

        st.dataframe(
            source_validation_df,
            use_container_width=True,
            hide_index=True
        )

        if (
            source_validation_df["Status"] == "FAIL"
        ).any():
            st.error(
                "Source validation found an issue. "
                "Review the details above."
            )
        else:
            st.success(
                "Snowflake source validation passed."
            )

    # ======================================================
    # ARCHITECTURE
    # ======================================================

    st.subheader("🏗️ Project Architecture")


    st.markdown(
        """
        <div class="info-card">

        <b>AWS</b>
        <br>
        Data ingestion and cloud data platform

        <br><br>

        ↓

        <br><br>

        <b>Snowflake</b>
        <br>
        Cloud data warehouse

        <br><br>

        ↓

        <br><br>

        <b>dbt</b>
        <br>
        Data transformation, testing, snapshots,
        incremental models, macros and analytics layers

        <br><br>

        ↓

        <br><br>

        <b>Bronze → Silver → Gold</b>
        <br>
        Structured analytical data layers

        <br><br>

        ↓

        <br><br>

        <b>Streamlit</b>
        <br>
        Interactive analytics and business dashboard

        </div>
        """,
        unsafe_allow_html=True
    )


    # ======================================================
    # TECHNOLOGY STACK
    # ======================================================

    st.subheader("🛠️ Technology Stack")


    tech_col1, tech_col2, tech_col3, tech_col4 = st.columns(4)


    with tech_col1:

        st.info(
            "☁️ **AWS**\n\n"
            "Cloud data platform"
        )


    with tech_col2:

        st.info(
            "❄️ **Snowflake**\n\n"
            "Data warehouse"
        )


    with tech_col3:

        st.info(
            "🔄 **dbt**\n\n"
            "Transformation layer"
        )


    with tech_col4:

        st.info(
            "📊 **Streamlit**\n\n"
            "Analytics application"
        )


    # ======================================================
    # STEP 24 — PROJECT VALIDATION CHECKLIST
    # ======================================================

    st.subheader("✅ Project Validation Checklist")


    validation_df = pd.DataFrame(
        {
            "Component": [
                "Snowflake Connection",
                "Gold OBT Table",
                "Global Date Filter",
                "Booking Status Filter",
                "Property Type Filter",
                "Executive KPIs",
                "Business Performance",
                "Analytics Charts",
                "Interactive Analytics",
                "Data Explorer",
                "Data Catalog",
                "CSV Export",
                "dbt Transformation Layer"
            ],
            "Status": [
                "✅ Active",
                "✅ Active",
                "✅ Active",
                "✅ Active",
                "✅ Active",
                "✅ Active",
                "✅ Active",
                "✅ Active",
                "✅ Active",
                "✅ Active",
                "✅ Active",
                "✅ Active",
                "✅ Active"
            ]
        }
    )


    st.dataframe(
        validation_df,
        use_container_width=True,
        hide_index=True
    )


# ==========================================================
# SNOWFLAKE CONNECTION DETAILS
# ==========================================================

st.markdown("---")


with st.expander(
    "🔐 Snowflake Connection Details"
):

    st.markdown(
        """
        <b>Data Source:</b> Snowflake &nbsp; | &nbsp;

        <b>Transformation:</b> dbt &nbsp; | &nbsp;

        <b>Cloud:</b> AWS &nbsp; | &nbsp;

        <b>Application:</b> Streamlit

        <br><br>

        Built as an end-to-end modern
        <b>Data Engineering & Analytics</b>
        portfolio project.
        """,
        unsafe_allow_html=True
    )


# ==========================================================
# FOOTER
# ==========================================================

st.markdown(
    """
    <div class="footer">

        AWS → Snowflake → dbt → Streamlit
        <br>
        Airbnb Analytics Intelligence Platform

    </div>
    """,
    unsafe_allow_html=True
)