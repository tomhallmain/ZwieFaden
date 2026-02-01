# ZwieFaden — Usage

How to install, run, and use the application: modes, shortcuts, and step-by-step instructions.

## Features

### Diff Mode
- Compare multiple code files side-by-side
- View unified diff format
- View HTML diff in browser
- Line-by-line comparison with syntax highlighting
- Side-by-side file comparison
- **LLM-powered version analysis**: Determine which version has the most up-to-date features
- **Automatic code generation**: Generate merged versions based on requirements
- Metadata collection: File paths, modification times, and context information

### Join Mode
- Analyze and group data from multiple text files
- Find similar entries across files
- Merge similar groupings
- Sort and browse confirmed and unconfirmed groupings

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Run the application:
```bash
python app.py
```

### Keyboard Shortcuts
- `Ctrl+1`: Switch to Join Mode
- `Ctrl+2`: Switch to Diff Mode

### Join Mode

1. Click "Add File" to add text files for analysis
2. Click "Start Analysis" to perform the join analysis
3. View groupings in the left panel
4. Double-click items to see details
5. Use "Toggle View Mode" to switch between confirmed and unconfirmed groupings
6. Use "Store Data" to save your progress
7. Use "Analysis Output" to generate analysis reports

### Diff Mode

#### Basic Diff Comparison
1. Click "Add File" to add files for comparison
2. Select two files from the dropdown menus
3. View the diff in the main panel:
   - Left side: Line-by-line diff with color coding
   - Right side: Side-by-side file comparison
4. Click "Show Unified Diff" for standard unified diff format
5. Click "Show HTML Diff" to open an HTML diff in your browser

#### LLM Analysis (Version Recommendation)
1. Add multiple versions of a tool module (2+ files)
2. Switch to the "LLM Analysis" tab
3. Enter the **Target Context**: Describe the application/context where you want to use this tool
4. Optionally enter **Specific Requirements**: Any constraints or requirements for the new version
5. Click **"Analyze Versions"** to:
   - Generate a cross-file diff matrix
   - Analyze all versions with metadata (modification times, paths, etc.)
   - Get LLM recommendations on which version is most up-to-date
   - See feature analysis and recommendations
6. The analysis will recommend the best file to use as a base

#### Generate Merged Version
1. After running analysis (or manually), click **"Generate Merged Version"**
2. Optionally select a **Base File** to use as the starting point
3. The LLM will generate a new version that:
   - Incorporates the best features from all versions
   - Is appropriate for your target context
   - Meets your specified requirements
4. Review the generated code in the right panel
5. Click **"Save Generated Code"** to save to a file

## Architecture

- `app.py`: Main application with mode switching
- `modes/join_mode.py`: Join/grouping mode widget
- `modes/diff_mode.py`: Diff comparison mode widget with LLM analysis
- `diff/diff_engine.py`: Core diff engine with metadata collection
- `diff/llm_analyzer.py`: LLM-based version analyzer and code generator
- `extensions/llm.py`: LLM interface (Ollama)
- `join/join.py`: Core join/grouping engine (existing)

## Notes

- Data is stored in `configs/join_multi_store.pkl` for Join Mode
- HTML diffs are saved as temporary files and opened in your default browser
- **LLM Analysis requires Ollama**: Make sure Ollama is running locally with a compatible model (default: `deepseek-r1:14b`)
- The LLM analyzer collects file metadata including modification times and directory context to help determine version recency
- Generated code can be saved directly to files for integration into your project

