import streamlit as st
import requests
import os
import urllib.parse

# API endpoints
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
API_BASE = f"{BACKEND_URL}"

st.set_page_config(page_title="IP-SHAKTI Chat", page_icon="⚖️", layout="wide")

st.title("⚖️ IP-SHAKTI Legal Assistant")
st.markdown("Your Indian Intellectual Property Law Assistant.")

# ── Sidebar (must run before session creation so j_mode is available) ───────
with st.sidebar:
    st.header("⚙️ Agent Settings")
    st.markdown("Configure the behavior of the IP-SHAKTI Legal Assistant.")

    jurisdiction = st.radio(
        "Jurisdiction Mode",
        options=["National (India)", "International", "Both"],
        index=0,
        help="Select which IP laws to search against.",
    )

    # Map display label → backend value
    if jurisdiction.startswith("National"):
        j_mode = "national"
    elif jurisdiction == "International":
        j_mode = "international"
    else:
        j_mode = "both"

    st.session_state.jurisdiction_mode = j_mode

    st.selectbox(
        "Language",
        ["English", "Hindi"],
        index=0,
        help="UI and response language (Hindi translation coming soon in Phase 2)"
    )

    if st.button("Clear Session", type="primary"):
        st.session_state.session_id = None
        st.session_state.messages = []
        st.rerun()
        
    st.divider()
    st.caption("⚠️ **Disclaimer**: This tool is for educational purposes only and does not substitute a qualified IP attorney. Do not rely on this for legal decisions.")

# ── One-time initialisation ──────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_id" not in st.session_state or st.session_state.session_id is None:
    # Create session using the sidebar-selected jurisdiction
    try:
        session_url = f"{BACKEND_URL}/session"
        res = requests.post(
            session_url,
            json={"jurisdiction_mode": st.session_state.jurisdiction_mode},
            timeout=10,
        )
        res.raise_for_status()
        st.session_state.session_id = res.json().get("session_id")
    except Exception as e:
        st.error(f"Could not connect to backend to create session: {e}")
        st.session_state.session_id = "offline-session"


# ── Render chat history ──────────────────────────────────────────────────────
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant" and "trace" in message and message["trace"]:
            with st.status("⚙️ Agent Orchestration Trace", expanded=False):
                for step in message["trace"]:
                    if (
                        "✅" in step
                        or "✓" in step
                        or "started" in step.lower()
                        or "initiated" in step.lower()
                        or "returned" in step.lower()
                    ):
                        st.write(step)
                    else:
                        st.write(f"→ {step}")

        st.markdown(message["content"])

        if message.get("sources"):
            with st.expander("📚 View Reference Documents"):
                for i, source in enumerate(message["sources"]):
                    act_name = source.get("act_name", "Unknown Act")
                    doc_id = source.get("document_id", "")
                    snippet = source.get("snippet", source.get("chunk_text", ""))
                    section = source.get("section", "")
                    page_start = source.get("page_start", 1)
                    page_end = source.get("page_end", 1)
                    old_content = source.get("content", "")

                    pdf_url = ""
                    if doc_id:
                        search_base = snippet if snippet else old_content
                        search_text = search_base.replace("\n", " ")
                        search_param = urllib.parse.quote(search_text)
                        pdf_url = (
                            f"{BACKEND_URL}/static/pdfjs/web/viewer.html"
                            f"?file=/pdf/{doc_id}#page={page_start}&search={search_param}"
                        )

                    st.markdown(f"**Source {i+1}: {act_name}**")
                    if section:
                        st.markdown(f"*{section} (Pages {page_start}-{page_end})*")
                    elif old_content:
                        st.markdown(f"*{old_content}*")

                    if snippet:
                        st.info(f'"{snippet}"')

                    if pdf_url:
                        if st.button(
                            "Verify this act",
                            key=f"hist_btn_{message.get('id', id(message))}_src{i}",
                        ):
                            st.components.v1.iframe(pdf_url, height=600, scrolling=True)
                    st.divider()

        if message.get("live_evidence"):
            with st.expander("🌐 Live Factual Evidence"):
                for ev in message["live_evidence"]:
                    st.markdown(f"**{ev.get('title', 'Source')}**")
                    st.write(ev.get("snippet", ""))
                    if "url" in ev:
                        st.markdown(f"[Source Link]({ev['url']})")
                    st.divider()


# ── Helper ───────────────────────────────────────────────────────────────────
def format_ans(ans_dict, title="### Assessment") -> str:
    ans_text = f"{title}\n\n"
    if "answer" in ans_dict:
        ans_text += f"{ans_dict['answer']}\n\n"
    if "ip_regimes_applicable" in ans_dict:
        ans_text += f"**Applicable IP Regimes:**\n{ans_dict['ip_regimes_applicable']}\n\n"
    if "patentability_posture" in ans_dict:
        ans_text += f"**Patentability Posture:**\n{ans_dict['patentability_posture']}\n\n"
    if "abs_exposure" in ans_dict:
        ans_text += f"**Access & Benefit Sharing (ABS) Exposure:**\n{ans_dict['abs_exposure']}\n\n"
    if "tkdl_relevance" in ans_dict:
        ans_text += f"**TKDL Relevance:**\n{ans_dict['tkdl_relevance']}\n\n"
    if "regulatory_classification" in ans_dict:
        ans_text += f"**Regulatory Classification:**\n{ans_dict['regulatory_classification']}\n\n"
    if "standing_disclaimer" in ans_dict:
        ans_text += f"*{ans_dict['standing_disclaimer']}*"
    return ans_text


# ── React to user input ──────────────────────────────────────────────────────
if prompt := st.chat_input("Ask a question about Indian IP Law (e.g., Patents, Trademarks)..."):
    # Show user message immediately
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    data = None
    with st.status("🧠 Agents Thinking...", expanded=True) as status_container:
        st.write("Initializing IP-SHAKTI Pipeline...")
        try:
            response = requests.post(
                f"{BACKEND_URL}/chat",
                json={
                    "session_id": st.session_state.session_id,
                    "message": prompt,
                    "jurisdiction_mode": st.session_state.jurisdiction_mode,
                },
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            status_container.update(label="✅ Analysis Complete!", state="complete", expanded=False)
        except requests.exceptions.RequestException as e:
            status_container.update(label="❌ Error", state="error", expanded=False)
            st.error(f"Error communicating with backend. Is it running? Details: {e}")

    if data is None:
        # Error already shown inside the status block
        pass
    elif data.get("type") == "clarification":
        answer = f"I need a bit more clarification:\n\n{data.get('question')}"
        sources = []
        returned_category = "Clarification Needed"
        live_ev = []

        full_response = f"**Product Category:** {returned_category}\n\n{answer}"
        with st.chat_message("assistant"):
            st.markdown(full_response)
        st.session_state.messages.append({
            "role": "assistant",
            "content": full_response,
            "sources": [],
            "trace": data.get("execution_trace", []),
            "live_evidence": [],
        })
    else:
        # Normal answer or abstain
        answer = ""
        raw_citations = []
        mode = data.get("jurisdiction_mode", "national")

        if mode in ("national", "both"):
            ans_dict = data.get("national_answer") or {}
            if ans_dict:
                title = "### National Assessment" if mode == "both" else "### Assessment"
                answer += format_ans(ans_dict, title) + "\n\n"
            raw_citations.extend(data.get("national_citations", []))

        if mode in ("international", "both"):
            ans_dict = data.get("international_answer") or {}
            if ans_dict:
                if answer:
                    answer += "---\n\n"
                title = "### International Assessment" if mode == "both" else "### Assessment"
                answer += format_ans(ans_dict, title) + "\n\n"
            raw_citations.extend(data.get("international_citations", []))

        if not answer.strip():
            answer = "No answer provided."

        returned_category = data.get("formulation_category", "Unknown")
        live_ev = data.get("live_evidence", [])
        trace = data.get("execution_trace", [])

        sources = []
        for c in raw_citations:
            sources.append({
                "act_name": c.get("act_name"),
                "document_id": c.get("document_id"),
                "section": c.get("section_or_article"),
                "page_start": c.get("page_start", 1),
                "page_end": c.get("page_end", 1),
                "snippet": c.get("snippet", c.get("chunk_text", "")),
                "content": (
                    f"Section: {c.get('section_or_article')}\n"
                    f"Pages: {c.get('page_start')}-{c.get('page_end')}"
                ),
            })

        full_response = f"**Product Category:** {returned_category}\n\n{answer}"

        with st.chat_message("assistant"):
            if trace:
                with st.status("⚙️ Agent Orchestration Trace", expanded=False):
                    for step in trace:
                        if (
                            "✅" in step
                            or "✓" in step
                            or "started" in step.lower()
                            or "initiated" in step.lower()
                            or "returned" in step.lower()
                        ):
                            st.write(step)
                        else:
                            st.write(f"→ {step}")

            st.markdown(full_response)

            if sources:
                with st.expander("📚 View Reference Documents"):
                    msg_idx = len(st.session_state.messages)
                    for i, source in enumerate(sources):
                        act_name = source.get("act_name", "Unknown Act")
                        doc_id = source.get("document_id", "")
                        snippet = source.get("snippet", source.get("chunk_text", ""))
                        section = source.get("section", "")
                        page_start = source.get("page_start", 1)
                        page_end = source.get("page_end", 1)
                        old_content = source.get("content", "")

                        pdf_url = ""
                        if doc_id:
                            search_base = snippet if snippet else old_content
                            search_text = search_base.replace("\n", " ")
                            search_param = urllib.parse.quote(search_text)
                            pdf_url = (
                                f"{BACKEND_URL}/static/pdfjs/web/viewer.html"
                                f"?file=/pdf/{doc_id}#page={page_start}&search={search_param}"
                            )

                        st.markdown(f"**Source {i+1}: {act_name}**")
                        if section:
                            st.markdown(f"*{section} (Pages {page_start}-{page_end})*")
                        elif old_content:
                            st.markdown(f"*{old_content}*")

                        if snippet:
                            st.info(f'"{snippet}"')

                        if pdf_url:
                            if st.button("Verify this act", key=f"btn_msg{msg_idx}_src{i}"):
                                st.components.v1.iframe(pdf_url, height=600, scrolling=True)
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
            "live_evidence": live_ev,
        })
