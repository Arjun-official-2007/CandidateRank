# utils/jd.py — Simple job description ingestion and config augmentation.
"""
Utility to ingest a plain‑text job description and update scoring configuration
based on detected requirements. This is deliberately lightweight – it scans
for a few keyword sections and populates the global `config` module with the
extracted values.

The expected format in the description (case‑insensitive) is:

    REQUIRED SKILLS: skill1, skill2, ...
    NICE TO HAVE SKILLS: skillA, skillB, ...
    RELEVANT TITLES: title1, title2, ...
    TARGET EXPERIENCE: N years

If a line is missing the prefix it is ignored. The parser does not attempt any
natural‑language understanding beyond these simple patterns.
"""
import re
from pathlib import Path
from typing import List

def parse_job_description(path: str):
    """Parse a job description file and return extracted config values.

    Returns a dict with keys ``must_have``, ``nice_to_have``, ``titles`` and
    ``target_experience`` (float years). Missing sections yield empty lists or
    ``None`` for experience.
    """
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    result = {
        "must_have": [],
        "nice_to_have": [],
        "titles": [],
        "target_experience": None,
    

    # Helper to split comma‑separated lists and normalise whitespace
    def split_items(line: str) -> List[str]:
        return [item.strip().lower() for item in line.split(",") if item.strip()]

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith("required skills:"):
            result["must_have"] = split_items(line[len("required skills:"):])
        elif low.startswith("nice to have skills:"):
            result["nice_to_have"] = split_items(line[len("nice to have skills:"):])
        elif low.startswith("relevant titles:"):
            result["titles"] = split_items(line[len("relevant titles:"):])
        elif low.startswith("target experience:"):
            match = re.search(r"(\d+(?:\.\d*)?)", line)
            if match:
                result["target_experience"] = float(match.group(1))
    return result

def apply_to_config(parsed, config_module):
    """Mutate the supplied ``config_module`` in‑place using ``parsed`` values.

    Only non‑empty entries are applied so existing defaults remain untouched when the
    job description does not specify a particular field.
    """
    if parsed["must_have"]:
        config_module.MUST_HAVE_SKILLS = parsed["must_have"]
    if parsed["nice_to_have"]:
        config_module.NICE_TO_HAVE_SKILLS = parsed["nice_to_have"]
    if parsed["titles"]:
        # Treat the extracted titles as high‑relevance titles for simplicity.
        config_module.HIGH_RELEVANCE_TITLES = parsed["titles"]
    if parsed["target_experience"] is not None:
        config_module.EXPERIENCE_TARGET_YEARS = parsed["target_experience"]
