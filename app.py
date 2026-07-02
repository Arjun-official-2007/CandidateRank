import streamlit as st
import sys, os, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from rank import main as run_rank

st.set_page_config(page_title="CandidateRank-AI Sandbox", layout="wide")
st.title("CandidateRank-AI — Sandbox Demo")
st.caption("Rule-based candidate ranking · deterministic · CPU-only · accepts ≤100 candidates")

SAMPLE_PATH = "src/tests/fixtures/sample_candidates.jsonl"

source = st.radio("Input source", ["Use bundled sample", "Upload candidates.jsonl"])

candidates_path = None
if source == "Use bundled sample":
    candidates_path = SAMPLE_PATH
    st.info(f"Using {SAMPLE_PATH}")
else:
    uploaded = st.file_uploader("Upload a .jsonl file (≤100 candidates)", type="jsonl")
    if uploaded:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl")
        tmp.write(uploaded.read())
        tmp.close()
        candidates_path = tmp.name

if candidates_path and st.button("Run ranking pipeline"):
    with open(candidates_path, "r", encoding="utf-8") as f:
        n_candidates = sum(1 for line in f if line.strip())

    if n_candidates > 100:
        st.error(f"{n_candidates} candidates found — sandbox is capped at 100.")
    else:
        out_path = "output/sandbox_submission.csv"
        os.makedirs("output", exist_ok=True)

        with st.spinner(f"Scoring {n_candidates} candidates..."):
            run_rank(candidates_path, out_path, min_rows=n_candidates)

        st.success(f"Ranked {n_candidates} candidates in under 5s.")

        import csv
        with open(out_path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        st.dataframe(rows, use_container_width=True)

        with open(out_path, "rb") as f:
            st.download_button("Download submission.csv", f, file_name="submission.csv")

        audit_path = os.path.join(os.path.dirname(out_path), "honeypot_audit.log")
        if os.path.exists(audit_path):
            with open(audit_path, "r", encoding="utf-8") as f:
                audit_content = f.read()
            if audit_content.strip():
                with st.expander("Honeypot exclusions"):
                    st.text(audit_content)