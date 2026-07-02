import streamlit as st
import sys, os, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from rank import main as run_rank
import utils.jd as jd_utils
from scoring import config as scoring_config

st.set_page_config(page_title="CandidateRank-AI Sandbox", layout="wide")
st.title("CandidateRank-AI — Sandbox Demo")
st.caption("Rule-based candidate ranking · deterministic · CPU-only · accepts ≤100 candidates")

SAMPLE_PATH = "src/tests/fixtures/sample_candidates.jsonl"

# ---------------------------------------------------------------------------
# Snapshot the ORIGINAL config values at import time, once.
# apply_to_config() mutates scoring_config in place, so without a reset,
# JD #2 in the same session would inherit leftover overrides from JD #1
# instead of starting from the true hardcoded defaults.
# ---------------------------------------------------------------------------
_DEFAULT_CONFIG_SNAPSHOT = {
    "MUST_HAVE_SKILLS": list(scoring_config.MUST_HAVE_SKILLS),
    "NICE_TO_HAVE_SKILLS": list(scoring_config.NICE_TO_HAVE_SKILLS),
    "HIGH_RELEVANCE_TITLES": list(scoring_config.HIGH_RELEVANCE_TITLES),
    "EXPERIENCE_TARGET_YEARS": scoring_config.EXPERIENCE_TARGET_YEARS,
}


def reset_config_to_defaults():
    scoring_config.MUST_HAVE_SKILLS = list(_DEFAULT_CONFIG_SNAPSHOT["MUST_HAVE_SKILLS"])
    scoring_config.NICE_TO_HAVE_SKILLS = list(_DEFAULT_CONFIG_SNAPSHOT["NICE_TO_HAVE_SKILLS"])
    scoring_config.HIGH_RELEVANCE_TITLES = list(_DEFAULT_CONFIG_SNAPSHOT["HIGH_RELEVANCE_TITLES"])
    scoring_config.EXPERIENCE_TARGET_YEARS = _DEFAULT_CONFIG_SNAPSHOT["EXPERIENCE_TARGET_YEARS"]


# ---------------------------------------------------------------------------
# Candidate source
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Job description source — this was previously missing entirely, which meant
# every run silently scored against the hardcoded defaults in scoring/config.py
# ---------------------------------------------------------------------------
st.subheader("Job description")
jd_mode = st.radio(
    "Scoring taxonomy",
    ["Use default config (hardcoded in scoring/config.py)", "Upload job description (.txt)"],
)

jd_path = None
if jd_mode.startswith("Upload"):
    jd_file = st.file_uploader(
        "Upload a plain-text JD",
        type="txt",
        help=(
            "Expected sections (case-insensitive), each optional:\n"
            "REQUIRED SKILLS: skill1, skill2, ...\n"
            "NICE TO HAVE SKILLS: skillA, skillB, ...\n"
            "RELEVANT TITLES: title1, title2, ...\n"
            "TARGET EXPERIENCE: N years"
        ),
    )
    if jd_file:
        tmp_jd = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        tmp_jd.write(jd_file.read())
        tmp_jd.close()
        jd_path = tmp_jd.name
    else:
        st.warning("Upload a JD file, or switch back to default config, before running.")

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
can_run = candidates_path and (jd_path or jd_mode.startswith("Use default"))

if can_run and st.button("Run ranking pipeline"):
    with open(candidates_path, "r", encoding="utf-8") as f:
        n_candidates = sum(1 for line in f if line.strip())

    if n_candidates > 100:
        st.error(f"{n_candidates} candidates found — sandbox is capped at 100.")
    else:
        # Always reset first so this run starts from true defaults,
        # regardless of what a previous run in this session applied.
        reset_config_to_defaults()

        if jd_path:
            parsed = jd_utils.parse_job_description(jd_path)
            jd_utils.apply_to_config(parsed, scoring_config)

            with st.expander("Applied JD overrides", expanded=True):
                st.write("**Required skills:**", parsed["must_have"] or "(none found — kept default)")
                st.write("**Nice-to-have skills:**", parsed["nice_to_have"] or "(none found — kept default)")
                st.write("**Relevant titles:**", parsed["titles"] or "(none found — kept default)")
                st.write(
                    "**Target experience (years):**",
                    parsed["target_experience"]
                    if parsed["target_experience"] is not None
                    else f"(none found — kept default of {_DEFAULT_CONFIG_SNAPSHOT['EXPERIENCE_TARGET_YEARS']})",
                )
                if not any([parsed["must_have"], parsed["nice_to_have"], parsed["titles"], parsed["target_experience"]]):
                    st.error(
                        "None of the expected JD sections were found in the uploaded file. "
                        "Scoring will run against the hardcoded defaults — check the file format."
                    )
        else:
            st.info("No JD uploaded — scoring against hardcoded defaults in scoring/config.py.")

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