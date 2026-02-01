import re

from PySide6.QtGui import QTextCharFormat, QColor, QSyntaxHighlighter


def markdown_to_html(markdown_text: str) -> str:
    """Convert markdown text to HTML for display in QTextEdit."""
    if not markdown_text:
        return ""
    
    html = markdown_text
    
    # Process code blocks first (before escaping HTML)
    code_blocks = []
    def code_block_replacer(match):
        lang = match.group(1) or ''
        code = match.group(2)
        # Store the code block and return a placeholder
        placeholder = f"__CODE_BLOCK_{len(code_blocks)}__"
        code_blocks.append((placeholder, code))
        return placeholder
    
    # Extract code blocks
    html = re.sub(r'```(\w+)?\n(.*?)```', code_block_replacer, html, flags=re.DOTALL)
    
    # Escape HTML special characters (but not in code blocks)
    html = html.replace('&', '&amp;')
    html = html.replace('<', '&lt;')
    html = html.replace('>', '&gt;')
    
    # Restore code blocks (they're already escaped)
    for placeholder, code in code_blocks:
        escaped_code = code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        html = html.replace(placeholder, f'<pre style="background-color: #2d2d2d; padding: 10px; border-radius: 4px; overflow-x: auto; white-space: pre-wrap;"><code>{escaped_code}</code></pre>')
    
    # Headers
    html = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
    
    # Inline code (single backticks) - process after code blocks
    html = re.sub(r'`([^`]+)`', r'<code style="background-color: #2d2d2d; padding: 2px 4px; border-radius: 3px;">\1</code>', html)
    
    # Bold
    html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'__(.*?)__', r'<strong>\1</strong>', html)
    
    # Italic - only match when surrounded by whitespace or word boundaries to avoid matching underscores in code
    # Match single asterisk: must have whitespace/start/end before and after
    html = re.sub(r'(?<!\S)\*([^*\s]+)\*(?!\S)', r'<em>\1</em>', html)
    # Match single underscore: must have whitespace/start/end before and after (but not double underscores)
    html = re.sub(r'(?<![_\S])_([^_\s]+)_(?![_\S])', r'<em>\1</em>', html)
    
    # Links
    html = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2" style="color: #4CAF50;">\1</a>', html)
    
    # Lists
    lines = html.split('\n')
    in_list = False
    result_lines = []
    for line in lines:
        if re.match(r'^\s*[-*+]\s+', line):
            if not in_list:
                result_lines.append('<ul>')
                in_list = True
            content = re.sub(r'^\s*[-*+]\s+', '', line)
            result_lines.append(f'<li>{content}</li>')
        elif re.match(r'^\s*\d+\.\s+', line):
            if not in_list:
                result_lines.append('<ol>')
                in_list = True
            content = re.sub(r'^\s*\d+\.\s+', '', line)
            result_lines.append(f'<li>{content}</li>')
        else:
            if in_list:
                result_lines.append('</ul>' if '<ul>' in '\n'.join(result_lines[-10:]) else '</ol>')
                in_list = False
            result_lines.append(line)
    if in_list:
        result_lines.append('</ul>')
    html = '\n'.join(result_lines)
    
    # Paragraphs (double newlines)
    html = re.sub(r'\n\n+', '</p><p>', html)
    html = f'<p>{html}</p>'
    
    # Line breaks
    html = html.replace('\n', '<br>')
    
    # Wrap in HTML document with dark theme styling
    return f"""
    <html>
    <head>
        <style>
            body {{
                background-color: #232323;
                color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
                line-height: 1.6;
                padding: 10px;
            }}
            h1 {{ color: #4CAF50; margin-top: 20px; margin-bottom: 10px; }}
            h2 {{ color: #81C784; margin-top: 18px; margin-bottom: 8px; }}
            h3 {{ color: #A5D6A7; margin-top: 16px; margin-bottom: 6px; }}
            code {{
                font-family: 'Courier New', monospace;
                color: #FFD54F;
            }}
            pre {{
                font-family: 'Courier New', monospace;
                color: #E0E0E0;
                white-space: pre-wrap;
                word-wrap: break-word;
            }}
            a {{ color: #4CAF50; text-decoration: underline; }}
            a:hover {{ color: #81C784; }}
            ul, ol {{ margin-left: 20px; }}
            li {{ margin-bottom: 5px; }}
        </style>
    </head>
    <body>
        {html}
    </body>
    </html>
    """

class DiffHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for diff output."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Define formats - using light colors visible on dark background
        self.insert_format = QTextCharFormat()
        self.insert_format.setForeground(QColor(100, 255, 100))  # Light green
        self.insert_format.setBackground(QColor(0, 80, 0))  # Dark green background
        
        self.delete_format = QTextCharFormat()
        self.delete_format.setForeground(QColor(255, 100, 100))  # Light red
        self.delete_format.setBackground(QColor(80, 0, 0))  # Dark red background
        
        self.equal_format = QTextCharFormat()
        self.equal_format.setForeground(QColor(220, 220, 220))  # Light gray/white
        
        self.context_format = QTextCharFormat()
        self.context_format.setForeground(QColor(150, 200, 255))  # Light blue
        self.context_format.setBackground(QColor(30, 50, 70))  # Dark blue background
    
    def highlightBlock(self, text):
        """Highlight a block of text based on diff markers."""
        if text.startswith('+') and not text.startswith('+++'):
            self.setFormat(0, len(text), self.insert_format)
        elif text.startswith('-') and not text.startswith('---'):
            self.setFormat(0, len(text), self.delete_format)
        elif text.startswith('@@'):
            self.setFormat(0, len(text), self.context_format)
        elif text.startswith(' ') or text == '':
            self.setFormat(0, len(text), self.equal_format)

