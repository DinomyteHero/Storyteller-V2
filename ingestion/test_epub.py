"""Unit tests for EPUB extraction."""
import unittest
import zipfile
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.epub_reader import read_epub, html_to_text


class TestEPUBReader(unittest.TestCase):
    """Test EPUB reading functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_epub_path = Path(__file__).parent.parent / "sample_data" / "test_book.epub"

        # Create test EPUB if missing or corrupt
        needs_rebuild = not self.test_epub_path.exists()
        if not needs_rebuild:
            try:
                zipfile.ZipFile(self.test_epub_path, "r").close()
            except zipfile.BadZipFile:
                needs_rebuild = True
        if needs_rebuild:
            from ingestion.create_test_epub import create_test_epub
            self.test_epub_path.parent.mkdir(parents=True, exist_ok=True)
            create_test_epub(self.test_epub_path)
    
    def test_read_epub_metadata(self):
        """Test that EPUB metadata is extracted correctly."""
        book_title, author, full_text, chapters = read_epub(self.test_epub_path)
        
        self.assertIsNotNone(book_title)
        self.assertEqual(book_title, "Test Legacy of the Force Book")
        self.assertEqual(author, "Test Author")
        self.assertIsInstance(chapters, list)
        self.assertGreater(len(chapters), 0)
    
    def test_read_epub_chapters(self):
        """Test that chapters are extracted correctly."""
        book_title, author, full_text, chapters = read_epub(self.test_epub_path)
        
        self.assertGreaterEqual(len(chapters), 2, "Should have at least 2 chapters")
        
        # Check chapter structure
        for chapter_title, chapter_text in chapters:
            self.assertIsInstance(chapter_title, str)
            self.assertIsInstance(chapter_text, str)
            self.assertGreater(len(chapter_text), 0)
        
        # Check first chapter
        first_title, first_text = chapters[0]
        self.assertIn("Chapter 1", first_title)
        self.assertIn("Jedi Council", first_text)
    
    def test_html_to_text(self):
        """Test HTML to text conversion."""
        html = """
        <html>
        <head><title>Test</title></head>
        <body>
            <h1>Chapter 1</h1>
            <p>This is a paragraph.</p>
            <p>Another paragraph.</p>
        </body>
        </html>
        """
        
        text = html_to_text(html)
        
        self.assertIn("Chapter 1", text)
        self.assertIn("This is a paragraph", text)
        self.assertIn("Another paragraph", text)
        # Should not contain HTML tags
        self.assertNotIn("<p>", text)
        self.assertNotIn("</p>", text)
    
    def test_chapter_titles_extracted(self):
        """Test that chapter titles are properly extracted."""
        book_title, author, full_text, chapters = read_epub(self.test_epub_path)
        
        # Check that chapter titles are meaningful
        titles = [title for title, _ in chapters]
        self.assertTrue(any("Chapter 1" in title for title in titles))
        self.assertTrue(any("Chapter 2" in title for title in titles))


if __name__ == "__main__":
    unittest.main()
