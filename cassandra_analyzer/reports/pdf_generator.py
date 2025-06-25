"""
PDF generator for converting markdown reports to PDF
"""

import os
from pathlib import Path
from typing import Optional
import structlog

try:
    import markdown
    from weasyprint import HTML, CSS
    from weasyprint.text.fonts import FontConfiguration
    from bs4 import BeautifulSoup
    PDF_AVAILABLE = True
except ImportError as e:
    PDF_AVAILABLE = False
    # Don't raise immediately - let the user know when they try to use it
    _pdf_import_error = e

logger = structlog.get_logger()


class PDFGenerator:
    """Generates PDF reports from markdown files"""
    
    def __init__(self):
        self.pdf_available = PDF_AVAILABLE
        if PDF_AVAILABLE:
            self.font_config = FontConfiguration()
        else:
            self.font_config = None
        
    def generate_pdf(self, markdown_path: Path, pdf_path: Optional[Path] = None) -> Path:
        """
        Convert a markdown file to PDF
        
        Args:
            markdown_path: Path to the markdown file
            pdf_path: Optional path for the PDF output. If not provided, 
                     uses the same name as markdown with .pdf extension
                     
        Returns:
            Path to the generated PDF file
        """
        if not self.pdf_available:
            import sys
            if getattr(sys, 'frozen', False):
                # Running in a PyInstaller bundle
                raise ImportError(
                    "PDF generation is not available in standalone executables. "
                    "Please use the markdown output or run from source with WeasyPrint installed. "
                    "See: https://github.com/axonops/cassandra-analyzer#pdf-generation"
                )
            else:
                # Running from source
                raise ImportError(
                    "PDF generation dependencies not installed. "
                    "Install with: pip install weasyprint markdown beautifulsoup4"
                ) from _pdf_import_error
        
        if not markdown_path.exists():
            raise FileNotFoundError(f"Markdown file not found: {markdown_path}")
            
        # Determine output path
        if pdf_path is None:
            pdf_path = markdown_path.with_suffix('.pdf')
            
        logger.info("Generating PDF from markdown", 
                   markdown_file=str(markdown_path),
                   pdf_file=str(pdf_path))
        
        # Read markdown content
        with open(markdown_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
            
        # Convert markdown to HTML
        md = markdown.Markdown(extensions=[
            'markdown.extensions.tables',
            'markdown.extensions.fenced_code',
            'markdown.extensions.codehilite',
            'markdown.extensions.toc',
            'markdown.extensions.nl2br',
            'markdown.extensions.sane_lists',
            'markdown.extensions.smarty'
        ])
        
        html_content = md.convert(markdown_content)
        
        # Post-process HTML to handle special elements
        html_content = self._post_process_html(html_content)
        
        # Wrap in complete HTML document with styling
        full_html = self._create_html_document(html_content)
        
        # Generate PDF
        css = CSS(string=self._get_css_styles(), font_config=self.font_config)
        
        HTML(string=full_html, base_url=str(markdown_path.parent)).write_pdf(
            pdf_path,
            stylesheets=[css],
            font_config=self.font_config
        )
        
        logger.info("PDF generated successfully", 
                   pdf_file=str(pdf_path),
                   size_bytes=pdf_path.stat().st_size)
        
        return pdf_path
    
    def _post_process_html(self, html: str) -> str:
        """Post-process HTML to handle special markdown elements"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Handle emoji characters by replacing with text equivalents
        emoji_replacements = {
            '🔴': '[CRITICAL]',
            '🟡': '[WARNING]',
            '🔵': '[INFO]',
            '✅': '[OK]',
            '❌': '[NO]',
            '⚠️': '[ALERT]',
            '⚪': '[N/A]',
            '🖥️': '[INFRASTRUCTURE]',
            '⚙️': '[CONFIGURATION]',
            '📊': '[OPERATIONS]',
            '📐': '[DATA MODEL]',
            '🔐': '[SECURITY]',
            '🔧': '[EXTENDED CONFIG]',
            '❓': '[UNKNOWN]'
        }
        
        # Replace emojis in text
        for element in soup.find_all(text=True):
            if element.parent.name not in ['script', 'style']:
                text = str(element)
                for emoji, replacement in emoji_replacements.items():
                    text = text.replace(emoji, replacement)
                element.replace_with(text)
        
        # Process tables to add classes for better styling
        for table in soup.find_all('table'):
            # Count columns
            first_row = table.find('tr')
            if first_row:
                col_count = len(first_row.find_all(['th', 'td']))
                if col_count >= 8:
                    table['class'] = table.get('class', []) + ['very-wide-table']
                elif col_count >= 6:
                    table['class'] = table.get('class', []) + ['wide-table']
                    
            # Check if table contains schema definitions (CQL)
            for cell in table.find_all('td'):
                if cell.find('code') and 'CREATE TABLE' in cell.get_text():
                    table['class'] = table.get('class', []) + ['schema-table']
                    # Break long schema definitions into multiple lines
                    for code in cell.find_all('code'):
                        text = code.get_text()
                        if len(text) > 100:
                            # Add line breaks after commas in CREATE TABLE statements
                            formatted_text = text.replace(', ', ',\n    ')
                            formatted_text = formatted_text.replace('(', '(\n    ')
                            formatted_text = formatted_text.replace(')', '\n)')
                            code.string = formatted_text
        
        return str(soup)
    
    def _create_html_document(self, content: str) -> str:
        """Create a complete HTML document with the content"""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Cassandra Cluster Analysis Report</title>
</head>
<body>
    <div class="container">
        {content}
    </div>
</body>
</html>
"""
    
    def _get_css_styles(self) -> str:
        """Get CSS styles for the PDF"""
        return """
/* Base styles */
@page {
    size: A4 landscape;
    margin: 1.5cm;
    @top-right {
        content: "Page " counter(page) " of " counter(pages);
        font-size: 10pt;
        color: #666;
    }
}

/* Alternative portrait page for sections without wide tables */
@page portrait {
    size: A4 portrait;
    margin: 2cm;
}

/* Apply portrait to title and summary sections */
h1:first-of-type {
    page: portrait;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 11pt;
    line-height: 1.6;
    color: #333;
}

.container {
    max-width: 100%;
}

/* Headers */
h1 {
    font-size: 24pt;
    color: #1a1a1a;
    margin-top: 0;
    margin-bottom: 20pt;
    page-break-after: avoid;
}

h2 {
    font-size: 18pt;
    color: #2c3e50;
    margin-top: 24pt;
    margin-bottom: 12pt;
    page-break-after: avoid;
}

h3 {
    font-size: 14pt;
    color: #34495e;
    margin-top: 18pt;
    margin-bottom: 10pt;
    page-break-after: avoid;
}

h4 {
    font-size: 12pt;
    color: #34495e;
    margin-top: 12pt;
    margin-bottom: 8pt;
    page-break-after: avoid;
}

/* Paragraphs and text */
p {
    margin-bottom: 10pt;
    text-align: justify;
}

strong {
    font-weight: 600;
    color: #2c3e50;
}

em {
    font-style: italic;
}

/* Links */
a {
    color: #3498db;
    text-decoration: none;
}

/* Lists */
ul, ol {
    margin-bottom: 10pt;
    padding-left: 20pt;
}

li {
    margin-bottom: 4pt;
}

/* Tables */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 12pt 0;
    font-size: 9pt;
    page-break-inside: auto;
    table-layout: fixed;
}

th {
    background-color: #f8f9fa;
    color: #2c3e50;
    font-weight: 600;
    padding: 6pt 4pt;
    text-align: left;
    border: 1px solid #dee2e6;
    word-wrap: break-word;
    overflow-wrap: break-word;
    vertical-align: top;
}

td {
    padding: 4pt;
    border: 1px solid #dee2e6;
    word-wrap: break-word;
    overflow-wrap: break-word;
    word-break: break-word;
    vertical-align: top;
    max-width: 0;
}

tr:nth-child(even) {
    background-color: #f8f9fa;
}

/* Special handling for wide content in tables */
td code, th code {
    font-size: 8pt;
    word-break: break-all;
}

/* Column width hints for common table types */
table th:first-child,
table td:first-child {
    width: 20%;
    min-width: 80pt;
}

/* For tables with many columns, use smaller font */
table:has(th:nth-child(6)) {
    font-size: 8pt;
}

table:has(th:nth-child(8)) {
    font-size: 7pt;
}

/* Schema tables need special handling */
table td:has(> code:only-child) {
    font-family: "Consolas", "Monaco", monospace;
    font-size: 7pt;
}

/* Wide table handling */
.wide-table {
    font-size: 8pt;
}

.very-wide-table {
    font-size: 7pt;
}

.schema-table {
    table-layout: auto;
}

.schema-table td {
    white-space: pre-wrap;
    font-family: "Consolas", "Monaco", monospace;
    font-size: 7pt;
}

/* Code blocks */
pre {
    background-color: #f5f5f5;
    border: 1px solid #ddd;
    border-radius: 3pt;
    padding: 8pt;
    font-family: "Consolas", "Monaco", "Courier New", monospace;
    font-size: 8pt;
    overflow-wrap: break-word;
    white-space: pre-wrap;
    margin: 10pt 0;
    page-break-inside: auto;
}

code {
    background-color: #f5f5f5;
    padding: 1pt 3pt;
    border-radius: 2pt;
    font-family: "Consolas", "Monaco", "Courier New", monospace;
    font-size: 8pt;
    word-break: break-all;
}

/* Horizontal rules */
hr {
    border: none;
    border-top: 1px solid #dee2e6;
    margin: 20pt 0;
}

/* Page breaks */
.page-break {
    page-break-before: always;
}

/* Status indicators */
.critical {
    color: #dc3545;
    font-weight: 600;
}

.warning {
    color: #ffc107;
    font-weight: 600;
}

.info {
    color: #17a2b8;
    font-weight: 600;
}

.success {
    color: #28a745;
    font-weight: 600;
}

/* Summary boxes */
.summary-box {
    background-color: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 4pt;
    padding: 12pt;
    margin: 12pt 0;
    page-break-inside: avoid;
}

/* Ensure certain elements don't break across pages */
h1, h2, h3, h4, h5, h6 {
    page-break-after: avoid;
}

table, figure, .summary-box {
    page-break-inside: avoid;
}

/* Keep related elements together */
h3 + table,
h4 + table,
h3 + p,
h4 + p {
    page-break-before: avoid;
}
"""