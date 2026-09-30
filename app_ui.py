import streamlit as st

from app.workflows.investigation_workflow import run_investigation
from app.review.human_review import HumanReviewGate
from app.schemas.review import ReviewDecision, ReviewRequest


# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------

st.set_page_config(
    page_title="MedVision AI V3",
    page_icon="🧠",
    layout="wide",
)


# ---------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------

if "result" not in st.session_state:
    st.session_state.result = None

if "state" not in st.session_state:
    st.session_state.state = None

if "decision" not in st.session_state:
    st.session_state.decision = None


# ---------------------------------------------------------
# HEADER
# ---------------------------------------------------------

st.title("🧠 MedVision AI V3")
st.caption(
    "Human-in-the-loop Agentic Engineering Platform"
)

st.markdown(
    """
    This workflow demonstrates:

    **Task → Investigation Agent → Evidence → Human Review → Approval**
    """
)


# ---------------------------------------------------------
# INVESTIGATION INPUT
# ---------------------------------------------------------

st.subheader("🔍 Investigation")

with st.form("investigation_form"):

    repo_path = st.text_input(
        "Repository Path",
        value="/Users/akshitchoudhary/MedVision-AI-v2.0-Production-AI-Inference-Platform",
    )

    prompt = st.text_area(
        "Investigation Task",
        value="Investigate how Redis is used in the repository.",
        height=100,
    )

    submitted = st.form_submit_button(
        "🚀 Run Investigation"
    )


# ---------------------------------------------------------
# RUN AGENT
# ---------------------------------------------------------

if submitted:

    # Reset previous review
    st.session_state.result = None
    st.session_state.state = None
    st.session_state.decision = None

    if not repo_path.strip():
        st.error("Repository path cannot be empty.")

    elif not prompt.strip():
        st.error("Investigation task cannot be empty.")

    else:

        with st.spinner(
            "Investigation Agent is analyzing the repository..."
        ):

            try:

                # IMPORTANT:
                # Workflow now returns BOTH result and state.
                result, state = run_investigation(
                    prompt=prompt,
                    repo_path=repo_path,
                )

                st.session_state.result = result
                st.session_state.state = state

            except Exception as exc:

                st.error(
                    f"Investigation failed: {exc}"
                )


# ---------------------------------------------------------
# RESULT
# ---------------------------------------------------------

result = st.session_state.result
state = st.session_state.state


if result is not None and state is not None:

    st.divider()

    st.subheader("📋 Investigation Result")


    # -----------------------------------------------------
    # FINDINGS
    # -----------------------------------------------------

    st.markdown("### Finding")

    if result.findings:

        for finding in result.findings:

            st.markdown(f"- {finding}")

    else:

        st.info("No findings were returned.")


    # -----------------------------------------------------
    # EVIDENCE
    # -----------------------------------------------------

    st.markdown("### 📁 Evidence — Files Actually Inspected")

    if result.evidence:

        for file_path in result.evidence:

            st.code(
                file_path,
                language="text",
            )

    else:

        st.warning(
            "No evidence files were recorded."
        )


    # -----------------------------------------------------
    # ERRORS
    # -----------------------------------------------------

    if result.errors:

        st.markdown("### ⚠️ Errors")

        for error in result.errors:

            st.error(error)


    # -----------------------------------------------------
    # RISK
    # -----------------------------------------------------

    st.markdown("### Risk")

    risk_level = str(result.risk_level.value)

    if risk_level == "low":

        st.success("🟢 LOW")

    elif risk_level == "medium":

        st.warning("🟡 MEDIUM")

    else:

        st.error("🔴 HIGH")


    # -----------------------------------------------------
    # APPROVAL REQUIREMENT
    # -----------------------------------------------------

    if result.requires_human_approval:

        st.info(
            "Human approval is required before this workflow can continue."
        )

    else:

        st.success(
            "Human approval is not required."
        )


    # -----------------------------------------------------
    # CURRENT STATE
    # -----------------------------------------------------

    st.markdown("### ⚙️ Agent State")

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "Agent Status",
            state.status.value,
        )

    with col2:

        st.metric(
            "Workflow State",
            state.workflow_state.value,
        )

    with col3:

        st.metric(
            "Current Step",
            state.current_step or "N/A",
        )


    # -----------------------------------------------------
    # HUMAN REVIEW
    # -----------------------------------------------------

    st.divider()

    st.subheader("👤 Human Review Gate")

    # If no decision has been made yet
    if st.session_state.decision is None:

        st.write(
            "Review the findings and evidence before making a decision."
        )

        col1, col2, col3 = st.columns(3)


        # -------------------------------------------------
        # APPROVE
        # -------------------------------------------------

        with col1:

            if st.button(
                "✅ Approve",
                use_container_width=True,
            ):

                review_gate = HumanReviewGate()

                review_request = ReviewRequest(
                    task_id=result.task_id,
                    decision=ReviewDecision.APPROVE,
                    reviewer="human",
                    comment="Reviewed findings and evidence.",
                )

                review_gate.review(
                    state=st.session_state.state,
                    result=result,
                    request=review_request,
                )

                st.session_state.decision = "approved"

                st.rerun()


        # -------------------------------------------------
        # REQUEST CHANGES
        # -------------------------------------------------

        with col2:

            if st.button(
                "🔄 Request Changes",
                use_container_width=True,
            ):

                review_gate = HumanReviewGate()

                review_request = ReviewRequest(
                    task_id=result.task_id,
                    decision=ReviewDecision.REQUEST_CHANGES,
                    reviewer="human",
                    comment="Changes requested after review.",
                )

                review_gate.review(
                    state=st.session_state.state,
                    result=result,
                    request=review_request,
                )

                st.session_state.decision = "changes_requested"

                st.rerun()


        # -------------------------------------------------
        # REJECT
        # -------------------------------------------------

        with col3:

            if st.button(
                "❌ Reject",
                use_container_width=True,
            ):

                review_gate = HumanReviewGate()

                review_request = ReviewRequest(
                    task_id=result.task_id,
                    decision=ReviewDecision.REJECT,
                    reviewer="human",
                    comment="Investigation rejected after review.",
                )

                review_gate.review(
                    state=st.session_state.state,
                    result=result,
                    request=review_request,
                )

                st.session_state.decision = "rejected"

                st.rerun()


    # -----------------------------------------------------
    # REVIEW RESULT
    # -----------------------------------------------------

    else:

        decision = st.session_state.decision

        if decision == "approved":

            st.success(
                "✅ Approved by human reviewer"
            )

        elif decision == "changes_requested":

            st.warning(
                "🔄 Changes requested by human reviewer"
            )

        elif decision == "rejected":

            st.error(
                "❌ Rejected by human reviewer"
            )


        # Show actual state after HumanReviewGate
        st.markdown("### Final Workflow State")

        st.code(
            state.workflow_state.value,
            language="text",
        )

        st.caption(
            "This decision is recorded in the agent workflow state."
        )


# ---------------------------------------------------------
# EMPTY STATE
# ---------------------------------------------------------

else:

    st.info(
        "Enter an investigation task and run the Investigation Agent."
    )