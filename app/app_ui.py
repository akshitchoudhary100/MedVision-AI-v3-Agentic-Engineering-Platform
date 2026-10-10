"""
MedVision V3 — Agentic Investigation Demo UI

Run with:
    streamlit run app_ui.py

Requires:
    pip install streamlit --break-system-packages   (or in your venv)

Assumes you've refactored your orchestration call into a single function:
    app.workflows.investigation_workflow.run_investigation(prompt, repo_path) -> AgentResult

If your function/module names differ, just fix the import below —
everything else in this file works against the AgentResult contract only.
"""

import streamlit as st

from app.workflows.investigation_workflow import run_investigation

st.set_page_config(page_title="MedVision V3 — Agentic Investigation", layout="centered")

st.title("🔎 MedVision V3 — Repository Investigation Agent")
st.caption(
    "Human-in-the-loop agentic engineering: the agent investigates, "
    "cites only files it actually read, and a human approves before "
    "anything is treated as final."
)

if "result" not in st.session_state:
    st.session_state.result = None
if "decision" not in st.session_state:
    st.session_state.decision = None

with st.form("investigate_form"):
    repo_path = st.text_input(
        "Repository path",
        value="/Users/akshitchoudhary/MedVision-AI-v2.0-Production-AI-Inference-Platform",
    )
    prompt = st.text_area(
        "Investigation question",
        value="Investigate Redis usage in the repository.",
        height=80,
    )
    submitted = st.form_submit_button("Run investigation")

if submitted:
    st.session_state.decision = None
    with st.spinner("Agent is searching and reading source files..."):
        try:
            st.session_state.result = run_investigation(prompt, repo_path)
        except Exception as e:
            st.session_state.result = None
            st.error(f"Investigation failed: {e}")

result = st.session_state.result

if result is not None:
    st.divider()
    st.subheader("Finding")
    for finding in result.findings:
      st.markdown(finding)

    st.subheader("Evidence — files actually inspected")
    for f in result.evidence:
        st.code(f, language="text")

    risk_color = {"low": "green", "medium": "orange", "high": "red"}.get(
        getattr(result.risk_level, "value", str(result.risk_level)).lower(), "gray"
    )
    st.markdown(
        f"**Risk level:** :{risk_color}[{result.risk_level}]  \n"
        f"**Human approval required:** {result.requires_human_approval}"
    )

    st.divider()
    st.subheader("Human Review Gate")

    if st.session_state.decision is None:
        col1, col2, col3 = st.columns(3)
        if col1.button("✅ Approve", use_container_width=True):
            st.session_state.decision = "approved"
            st.rerun()
        if col2.button("🔁 Request changes", use_container_width=True):
            st.session_state.decision = "changes_requested"
            st.rerun()
        if col3.button("❌ Reject", use_container_width=True):
            st.session_state.decision = "rejected"
            st.rerun()
    else:
        badge = {
            "approved": "✅ Approved by human reviewer",
            "changes_requested": "🔁 Changes requested — agent would be re-run with notes",
            "rejected": "❌ Rejected — pipeline stopped",
        }[st.session_state.decision]
        st.success(badge) if st.session_state.decision == "approved" else st.warning(badge)
        st.caption("This decision is what gates the pipeline in the orchestrator — nothing downstream runs without it.")

else:
    st.info("Enter a repository path and a question, then run the investigation.")