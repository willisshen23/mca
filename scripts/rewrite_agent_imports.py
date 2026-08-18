import re
from pathlib import Path

ROOT = Path("backend/src")

REPLACEMENTS = [
    (r"from src\.agent\.capabilities\.", "from src.report_pipeline.capabilities."),
    (r"import src\.agent\.capabilities", "import src.report_pipeline.capabilities"),
    (r"from src\.agent\.graph\.state", "from src.report_pipeline.state"),
    (r"from src\.agent\.graph\.request_scope", "from src.report_pipeline.defaults"),
    (r"from src\.agent\.prompts\.marketing_workflow", "from src.report_pipeline.prompts.marketing_workflow"),
]


def rewrite(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    new_text = text
    for pattern, repl in REPLACEMENTS:
        new_text = re.sub(pattern, repl, new_text)
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        print("rewrote", path)


for p in ROOT.rglob("*.py"):
    if "__pycache__" in p.parts:
        continue
    rewrite(p)
