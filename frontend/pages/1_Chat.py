import streamlit as st
import requests
import os
import urllib.parse
import os

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000/chat")

st.set_page_config(page_title="IP-SHAKTI Chat", page_icon="⚖️", layout="centered")

st.title("⚖️ IP-SHAKTI Legal Assistant")
st.markdown("Your Indian Intellectual Property Law Assistant.")

# Initialize session state for messages and session ID
if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_id" not in st.session_state:
    # Create a new session on the backend
    try:
        session_url = BACKEND_URL.replace("/chat", "/session")
        res = requests.post(session_url, json={"jurisdiction_mode": "national"}, timeout=10)
        res.raise_for_status()
        st.session_state.session_id = res.json().get("session_id")
    except Exception as e:
        st.error(f"Could not connect to backend to create session: {e}")
        st.session_state.session_id = "offline-session"

# Sidebar for Settings
with st.sidebar:
    st.header("⚙️ Agent Settings")
    st.markdown("Configure the behavior of the IP-SHAKTI Legal Assistant.")
    
    jurisdiction = st.radio(
        "Jurisdiction Mode",
        options=["National (India)", "International", "Both"],
        index=0,
        help="Select which IP laws to search against."
    )
    
    # Map to backend values
    if jurisdiction.startswith("National"):
        j_mode = "national"
    elif jurisdiction == "International":
        j_mode = "international"
    else:
        j_mode = "both"
        
    st.session_state.jurisdiction_mode = j_mode


# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant" and "trace" in message and message["trace"]:
            with st.status("⚙️ Agent Orchestration Trace", expanded=False):
                for step in message["trace"]:
                    if "✅" in step or "✓" in step or "started" in step.lower() or "initiated" in step.lower() or "returned" in step.lower():
                        st.write(step)
                    else:
                        st.write(f"→ {step}")
        
        st.markdown(message["content"])
        
        # Display sources if they exist in history
        if message.get("sources"):
            with st.expander("📚 View Reference Documents"):
                for i, source in enumerate(message["sources"]):
                    act_name = source.get("act_name", "Unknown Act")
                    doc_id = source.get("document_id", "")
                    content = source.get("content", "")
                    
                    pdf_url = ""
                    if doc_id:
                        search_text = content.replace('\n', ' ')[:60]
                        search_param = urllib.parse.quote(search_text)
                        pdf_url = f"http://localhost:8000/static/pdfjs/web/viewer.html?file=/pdf/{doc_id}#search={search_param}"
                        
                    header = f"**Source {i+1}: {act_name}**"
                    st.markdown(header)
                    if pdf_url:
                        if st.button(f"Embed Viewer for Source {i+1}", key=f"hist_btn_{message.get('id', id(message))}_src{i}"):
                            st.components.v1.iframe(pdf_url, height=600, scrolling=True)
                    st.markdown(f"*{content}*")
                    st.divider()

        if message.get("live_evidence"):
            with st.expander("🌐 Live Factual Evidence"):
                for ev in message["live_evidence"]:
                    st.markdown(f"**{ev.get('title', 'Source')}**")
                    st.write(ev.get("snippet", ""))
                    if "url" in ev:
                        st.markdown(f"[Source Link]({ev['url']})")
                    st.divider()

# React to user input
if prompt := st.chat_input("Ask a question about Indian IP Law (e.g., Patents, Trademarks)..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.status("🧠 Agents Thinking...", expanded=True) as status_container:
        st.write("Initializing IP-SHAKTI Pipeline...")
        try:
            # We add jurisdiction to the request
            response = requests.post(
                BACKEND_URL,
                json={
                    "session_id": st.session_state.session_id,
                    "message": prompt,
                    "jurisdiction_mode": st.session_state.jurisdiction_mode
                },
                timeout=120
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("type") == "clarification":
                answer = f"I need a bit more clarification:\n\n{data.get('question')}"
                sources = []
                returned_category = "Clarification Needed"
                live_ev = []
            else:
                ans_dict = data.get("national_answer", {}) or {}
                
                # Format the structured JSON response into a markdown answer
                if ans_dict:
                    answer = "### Assessment\n\n"
                    if "ip_regimes_applicable" in ans_dict:
                        answer += f"**Applicable IP Regimes:**\n{ans_dict['ip_regimes_applicable']}\n\n"
                    if "patentability_posture" in ans_dict:
                        answer += f"**Patentability Posture:**\n{ans_dict['patentability_posture']}\n\n"
                    if "abs_exposure" in ans_dict:
                        answer += f"**Access & Benefit Sharing (ABS) Exposure:**\n{ans_dict['abs_exposure']}\n\n"
                    if "tkdl_relevance" in ans_dict:
                        answer += f"**TKDL Relevance:**\n{ans_dict['tkdl_relevance']}\n\n"
                    if "regulatory_classification" in ans_dict:
                        answer += f"**Regulatory Classification:**\n{ans_dict['regulatory_classification']}\n\n"
                    if "standing_disclaimer" in ans_dict:
                        answer += f"*{ans_dict['standing_disclaimer']}*"
                else:
                    answer = "No answer provided."
                    
                returned_category = data.get("formulation_category", "Unknown")
                raw_citations = data.get("national_citations", [])
                live_ev = data.get("live_evidence", [])
                sources = []
                for c in raw_citations:
                    sources.append({
                        "act_name": c.get("act_name"),
                        "document_id": c.get("document_id"),
                        "content": f"Section: {c.get('section_or_article')}\nPages: {c.get('page_start')}-{c.get('page_end')}"
                    })
            
            full_response = f"**Product Category:** {returned_category}\n\n{answer}"
            
            
            status_container.update(label="✅ Analysis Complete!", state="complete", expanded=False)
            
            with st.chat_message("assistant"):
                trace = data.get("execution_trace", [])
                if trace:
                    with st.status("⚙️ Agent Orchestration Trace", expanded=False):
                        for step in trace:
                            if "✅" in step or "✓" in step or "started" in step.lower() or "initiated" in step.lower() or "returned" in step.lower():
                                st.write(step)
                            else:
                                st.write(f"→ {step}")
                                
                st.markdown(full_response)
                
                if sources:
                    with st.expander("📚 View Reference Documents"):
                        for i, source in enumerate(sources):
                            act_name = source.get("act_name", "Unknown Act")
                            doc_id = source.get("document_id", "")
                            content = source.get("content", "")
                            pdf_url = ""
                            if doc_id:
                                search_text = content.replace('\n', ' ')[:60]
                                search_param = urllib.parse.quote(search_text)
                                page_start = c.get('page_start', 1)
                                pdf_url = f"http://localhost:8000/static/pdfjs/web/viewer.html?file=/pdf/{doc_id}#page={page_start}&search={search_param}"
                            st.markdown(f"**Source {i+1}: {act_name}**")
                            if pdf_url:
                                msg_idx = len(st.session_state.messages)
                                if st.button(f"Embed Viewer for Source {i+1}", key=f"btn_msg{msg_idx}_src{i}"):
                                    st.components.v1.iframe(pdf_url, height=600, scrolling=True)
                            st.markdown(f"*{content}*")
                            st.divider()
                
                if live_ev:
                    with st.expander("🌐 Live Factual Evidence"):
                        for ev in live_ev:
                            st.markdown(f"**{ev.get('title', 'Source')}**")
                            st.write(ev.get("snippet", ""))
                            if "url" in ev:
                                st.markdown(f"[Source Link]({ev['url']})")
                            st.divider()
                
            st.session_state.messages.append({
                "role": "assistant", 
                "content": full_response, 
                "sources": sources, 
                "trace": trace, 
                "live_evidence": live_ev
            })
            
        except requests.exceptions.RequestException as e:
            st.error(f"Error communicating with backend. Is it running? Details: {e}")
