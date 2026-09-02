import streamlit as st
import sqlite3
import pandas as pd
import os

st.set_page_config(page_title="IP-SHAKTI Evaluation", page_icon="📊", layout="wide")

st.title("📊 IP-SHAKTI Evaluation Dashboard")
st.markdown("Monitor the performance, latency, and abstention rate of the RAG pipeline.")

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend", "query_log.db"))

@st.cache_data(ttl=5) # Refresh data every 5 seconds
def get_data():
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM query_log", conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Error loading database: {e}")
        return pd.DataFrame()

df = get_data()

if df.empty:
    st.info("No queries have been logged yet. Ask a question in the chat to populate this dashboard!")
else:
    # Handle potentially missing columns gracefully
    if 'abstain' not in df.columns:
        df['abstain'] = 0
    if 'latency_ms' not in df.columns:
        df['latency_ms'] = 0.0
    if 'confidence_score' not in df.columns:
        df['confidence_score'] = 0.0

    # Convert numeric columns safely
    df['abstain'] = pd.to_numeric(df['abstain'], errors='coerce').fillna(0)
    df['latency_ms'] = pd.to_numeric(df['latency_ms'], errors='coerce').fillna(0)
    df['confidence_score'] = pd.to_numeric(df['confidence_score'], errors='coerce').fillna(0)

    # High-level KPIs
    total_queries = len(df)
    abstained = df['abstain'].sum()
    abstention_rate = (abstained / total_queries) * 100 if total_queries > 0 else 0
    avg_latency = df['latency_ms'].mean()
    avg_confidence = df['confidence_score'].mean() * 100 # assuming 0-1 range

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Queries", total_queries)
    col2.metric("Abstention Rate", f"{abstention_rate:.1f}%")
    col3.metric("Avg Latency (ms)", f"{avg_latency:.0f}")
    col4.metric("Avg Confidence", f"{avg_confidence:.1f}%")

    st.divider()

    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.subheader("Abstention Reasons")
        abstain_df = df[df['abstain'] == 1]
        if not abstain_df.empty and 'abstain_reason' in abstain_df.columns:
            reason_counts = abstain_df['abstain_reason'].value_counts()
            st.bar_chart(reason_counts)
        else:
            st.write("No abstentions recorded yet.")

    with col_chart2:
        st.subheader("Formulation Categories")
        if 'formulation_category' in df.columns:
            st.bar_chart(df['formulation_category'].value_counts())
        else:
            st.write("No categories recorded yet.")

    st.divider()

    st.subheader("Query Log")
    
    # Select columns that exist in the dataframe
    display_cols = []
    for col in ['timestamp', 'raw_query', 'formulation_category', 'confidence_score', 'abstain', 'latency_ms', 'max_similarity']:
        if col in df.columns:
            display_cols.append(col)
            
    if display_cols:
        display_df = df[display_cols].copy()
        if 'timestamp' in display_df.columns:
            display_df = display_df.sort_values(by='timestamp', ascending=False)
        st.dataframe(display_df, use_container_width=True)
    else:
        st.write("No displayable data found.")
