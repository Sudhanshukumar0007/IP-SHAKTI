import os
from dotenv import load_dotenv

env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)

import streamlit as st

st.set_page_config(
    page_title="IP-SHAKTI",
    page_icon="⚖️",
    layout="centered"
)

st.title("⚖️ Welcome to IP-SHAKTI")
st.markdown("""
IP-SHAKTI is an agentic RAG-powered assistant for Ayurvedic traditional knowledge and Indian Intellectual Property Law.

### Navigation
Please select a tool from the sidebar:
- **💬 Chat**: Interact with the IP-SHAKTI legal assistant to classify formulations, determine jurisdiction, and retrieve legal & live factual evidence.
- **📊 Evaluation**: View the performance and usage logs of the RAG model.
""")
