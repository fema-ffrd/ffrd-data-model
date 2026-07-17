"""
Renders data-dictionary.yaml as a Markdown file grouped by domain.
Usage:  python3 preview_dict.py > data-dictionary.md
Then open data-dictionary.md and use VS Code Markdown Preview (Ctrl+Shift+V).
"""

import yaml
from pathlib import Path
from collections import defaultdict

src = Path(__file__).parent / "data-dictionary.yaml"
out = Path(__file__).parent / "data-dictionary.md"

with src.open() as f:
    dd = yaml.safe_load(f)

tables = dd.get("tables", {})

# Group by domain
domains = defaultdict(list)
for table_name, table_def in tables.items():
    domains[table_def.get("domain", "other")].append((table_name, table_def))

domain_order = ["events", "models", "structures", "management"]
constraint_labels = {"PK": "🔑", "FK": "🔗", "NN": "✱"}

lines = [
    "# FFRD Data Dictionary\n",
    "_Auto-generated from `data-dictionary.yaml`. Do not edit directly._\n",
    "---\n",
    "## Table of Contents\n",
]

for domain in domain_order:
    if domain not in domains:
        continue
    lines.append(f"- **{domain.title()}**")
    for table_name, _ in domains[domain]:
        anchor = table_name.replace("_", "-")
        lines.append(f"  - [{table_name}](#{anchor})")

lines.append("\n---\n")

for domain in domain_order:
    if domain not in domains:
        continue
    lines.append(f"## {domain.title()}\n")
    for table_name, table_def in domains[domain]:
        lines.append(f"### {table_name}\n")
        if "description" in table_def:
            lines.append(f"{table_def['description']}\n")
        cols = table_def.get("columns", {})
        if cols:
            lines.append("| Column | Type | Constraints | References | Description |")
            lines.append("|--------|------|-------------|------------|-------------|")
            for col_name, col in cols.items():
                ctype = col.get("type", "")
                constraints = col.get("constraints", [])
                badges = " ".join(constraint_labels.get(c, c) for c in constraints)
                ref = col.get("references", "")
                # Truncate long descriptions for table readability
                desc = str(col.get("description", "")).replace("\n", " ").strip()
                if len(desc) > 120:
                    desc = desc[:117] + "..."
                lines.append(
                    f"| `{col_name}` | `{ctype}` | {badges} | {ref} | {desc} |"
                )
        lines.append("")

with out.open("w") as f:
    f.write("\n".join(lines))

print(f"Written to {out}")
print(f"  {len(tables)} tables across {len(domains)} domains")
