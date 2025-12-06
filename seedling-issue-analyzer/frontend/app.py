import os
import json

import requests
import streamlit as st

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")


st.set_page_config(
    page_title="Seedling Issue Analyzer",
    layout="centered",
)

st.title("🌱 Seedling Labs – GitHub Issue Analyzer")

st.markdown(
    """
Paste a **public GitHub repo URL** and an **issue number**.  
We’ll fetch the issue, analyze it with an LLM, and return a structured JSON summary.
"""
)

with st.form("issue_form"):
    default_repo = "https://github.com/facebook/react"
    repo_url = st.text_input("GitHub Repository URL", value=default_repo)
    issue_number = st.number_input("Issue Number", min_value=1, step=1, value=1)
    submitted = st.form_submit_button("Analyze Issue 🚀")

if submitted:
    if not repo_url:
        st.error("Please provide a GitHub repository URL.")
    else:
        with st.spinner("Analyzing issue..."):
            try:
                resp = requests.post(
                    f"{API_BASE}/analyze",
                    json={"repo_url": repo_url, "issue_number": int(issue_number)},
                    timeout=60,
                )
            except requests.RequestException as e:
                st.error(f"Error contacting backend API: {e}")
            else:
                if resp.status_code != 200:
                    try:
                        detail = resp.json().get("detail", resp.text)
                    except Exception:
                        detail = resp.text
                    st.error(f"API returned {resp.status_code}: {detail}")
                else:
                    data = resp.json()
                    issue = data["issue"]
                    analysis = data["analysis"]

                    st.subheader("Issue Context")
                    st.write(f"**Title:** {issue['title']}")
                    st.write("**Body:**")
                    st.markdown(
                        issue["body"] if issue["body"] else "_No description provided._"
                    )

                    if issue["comments"]:
                        with st.expander(f"Comments ({len(issue['comments'])})"):
                            for i, c in enumerate(issue["comments"], start=1):
                                st.markdown(f"**Comment {i}:**\n\n{c}")
                    else:
                        st.caption("No comments on this issue yet.")

                    st.subheader("AI Triage Summary")

                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**Type:** `{analysis['type']}`")
                    with col2:
                        st.markdown(f"**Priority:** {analysis['priority_score']}")

                    st.markdown(f"**Summary:** {analysis['summary']}")
                    st.markdown(
                        f"**Suggested Labels:** "
                        + ", ".join(f"`{lbl}`" for lbl in analysis["suggested_labels"])
                    )
                    st.markdown(f"**Potential Impact:** {analysis['potential_impact']}")

                    st.divider()
                    st.subheader("Raw JSON Output")

                    pretty_json = json.dumps(analysis, indent=2)
                    st.code(pretty_json, language="json")

                    # Small bonus: "Copy JSON" button using a tiny JS hack
                    st.markdown(
                        f"""
                        <button onclick="navigator.clipboard.writeText({json.dumps(pretty_json)});">
                        Copy JSON to clipboard
                        </button>
                        """,
                        unsafe_allow_html=True,
                    )

st.caption(
    "Tip: Configure OPENAI_API_KEY and optional GITHUB_TOKEN as env vars before running."
)
