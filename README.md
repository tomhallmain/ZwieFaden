# ZwieFaden

A PySide6 app for comparing code files and merging versions with LLM help—plus a separate mode for text-file data analysis.

**Main focus:** Diff mode. Compare multiple versions of a file side-by-side, get LLM-backed recommendations on which is most up-to-date, and generate a merged version tailored to your context.

---

## Diff Mode — Code File Comparison

Compare code files, see what changed, and let the LLM suggest which version to use or how to merge them.

- **Side-by-side and unified diffs** — Line-by-line comparison with syntax highlighting, plus standard unified diff and HTML diff in the browser
- **LLM version analysis** — Add several versions of a module, describe your target context, and get recommendations on which version is most up-to-date (uses file metadata and content)
- **Generate merged code** — One click to produce a merged version that fits your context and requirements; review in-app and save to a file
- **Project Compare** — Point at two project directories and find every file they share, split into identical / different / only-in-one-side; open any differing pair directly in the diff view above

**Typical workflow:** Add 2+ versions of a file → run **Analyze Versions** with your target context → use **Generate Merged Version** (optionally pick a base file) → save the result.

LLM features use **Ollama** locally (default model: `deepseek-r1:14b`). Make sure Ollama is running.

---

## Join Mode — Data Analysis

For analyzing and grouping data across multiple text files: find similar entries, merge groupings, sort confirmed vs unconfirmed, and export. Based on the original `app.py` behavior; data is stored in `configs/join_multi_store.pkl`.

---

## Quick Start

```bash
pip install -r requirements.txt
python app.py
```

For detailed usage, keyboard shortcuts, and step-by-step instructions for both modes, see **USAGE.md**.
