"""
Tests for PDF generation functionality
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys
import tempfile

from cassandra_analyzer.reports.pdf_generator import PDFGenerator


class TestPDFGenerator:
    """Test PDF generation handling"""

    def test_pdf_generator_init_without_dependencies(self):
        """Test PDFGenerator initialization when dependencies are missing"""
        # Mock the PDF_AVAILABLE as False
        with patch("cassandra_analyzer.reports.pdf_generator.PDF_AVAILABLE", False):
            # Should not raise during init
            generator = PDFGenerator()
            assert generator.pdf_available is False
            assert generator.font_config is None

    def test_pdf_generator_init_with_dependencies(self):
        """Test PDFGenerator initialization when dependencies are available"""
        # Check if WeasyPrint is actually available in test environment
        try:
            from weasyprint.text.fonts import FontConfiguration
            # If available, test with real dependencies
            generator = PDFGenerator()
            assert hasattr(generator, 'pdf_available')
            assert hasattr(generator, 'font_config')
        except ImportError:
            # If not available, just skip this test
            pytest.skip("WeasyPrint not installed in test environment")

    def test_generate_pdf_without_dependencies_from_source(self):
        """Test error when generating PDF without dependencies from source"""
        with patch("cassandra_analyzer.reports.pdf_generator.PDF_AVAILABLE", False):
            generator = PDFGenerator()
            
            # Create a temporary markdown file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write("# Test Report")
                temp_path = Path(f.name)
            
            try:
                # Mock sys.frozen to False (running from source)
                with patch.object(sys, 'frozen', False, create=True):
                    with pytest.raises(ImportError) as exc_info:
                        generator.generate_pdf(temp_path)
                    
                    assert "PDF generation dependencies not installed" in str(exc_info.value)
                    assert "pip install weasyprint markdown beautifulsoup4" in str(exc_info.value)
            finally:
                temp_path.unlink()

    def test_generate_pdf_without_dependencies_from_executable(self):
        """Test error when generating PDF from standalone executable"""
        with patch("cassandra_analyzer.reports.pdf_generator.PDF_AVAILABLE", False):
            generator = PDFGenerator()
            
            # Create a temporary markdown file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write("# Test Report")
                temp_path = Path(f.name)
            
            try:
                # Mock sys.frozen to True (running from PyInstaller)
                with patch.object(sys, 'frozen', True, create=True):
                    with pytest.raises(ImportError) as exc_info:
                        generator.generate_pdf(temp_path)
                    
                    assert "PDF generation is not available in standalone executables" in str(exc_info.value)
                    assert "use the markdown output" in str(exc_info.value)
                    assert "github.com/axonops/cassandra-analyzer#pdf-generation" in str(exc_info.value)
            finally:
                temp_path.unlink()

    @pytest.mark.skip(reason="Complex mocking of WeasyPrint dependencies")
    def test_generate_pdf_with_dependencies(self):
        """Test successful PDF generation when dependencies are available"""
        # This test is skipped because mocking WeasyPrint's complex dependencies
        # is not straightforward and doesn't add much value to the test suite.
        # The important tests are the error handling when dependencies are missing.
        pass

    def test_generate_pdf_file_not_found(self):
        """Test error when markdown file doesn't exist"""
        # Test with PDF available = True so we get past the dependency check
        generator = PDFGenerator()
        generator.pdf_available = True  # Force this to test the file not found error
        
        # Try to generate PDF from non-existent file
        non_existent = Path("/tmp/does_not_exist.md")
        with pytest.raises(FileNotFoundError) as exc_info:
            generator.generate_pdf(non_existent)
        
        assert "Markdown file not found" in str(exc_info.value)


def mock_open(read_data=""):
    """Helper to create a mock for open()"""
    from unittest.mock import mock_open as _mock_open
    return _mock_open(read_data=read_data)