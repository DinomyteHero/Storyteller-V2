"""Script to create a minimal test EPUB file."""
import ebooklib
from ebooklib import epub
from pathlib import Path

def create_test_epub(output_path: Path):
    """Create a minimal test EPUB with chapters."""
    book = epub.EpubBook()
    
    # Set metadata
    book.set_identifier('test-book-123')
    book.set_title('Test Legacy of the Force Book')
    book.set_language('en')
    book.add_author('Test Author')
    
    # Chapter 1
    c1 = epub.EpubHtml(title='Chapter 1: The Beginning', file_name='chap01.xhtml', lang='en')
    c1.content = '''
    <html>
    <head><title>Chapter 1</title></head>
    <body>
        <h1>Chapter 1: The Beginning</h1>
        <p>The galaxy was in turmoil. The Legacy of the Force era had begun, and the fragile peace that had existed after the Yuuzhan Vong War was shattering. On Coruscant, the Jedi Council met in emergency session.</p>
        <p>Master Luke Skywalker stood before the assembled Jedi, his voice steady but carrying the weight of years of conflict. "The Sith have returned," he announced. "Darth Caedus has emerged, and he threatens everything we've built."</p>
    </body>
    </html>
    '''
    
    # Chapter 2
    c2 = epub.EpubHtml(title='Chapter 2: Shadows', file_name='chap02.xhtml', lang='en')
    c2.content = '''
    <html>
    <head><title>Chapter 2</title></head>
    <body>
        <h1>Chapter 2: Shadows</h1>
        <p>In the Outer Rim, on the planet of Kuat, a young Jedi Knight received a transmission. The message was encrypted, but the urgency was clear. Something was happening that would change the course of galactic history.</p>
        <p>The Jedi Knight's ship, a modified X-wing, dropped out of hyperspace near the coordinates provided in the transmission. The system was unknown, marked only as a potential Sith stronghold in ancient records.</p>
    </body>
    </html>
    '''
    
    # Add chapters to book
    book.add_item(c1)
    book.add_item(c2)
    
    # Create spine (reading order)
    book.spine = [c1, c2]
    
    # Add default NCX and Nav file
    book.toc = [
        c1,
        c2
    ]
    
    # Add navigation files
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    
    # Write the EPUB file
    epub.write_epub(str(output_path), book, {})
    print(f"Created test EPUB at {output_path}")

if __name__ == "__main__":
    output = Path(__file__).parent.parent / "sample_data" / "test_book.epub"
    output.parent.mkdir(exist_ok=True)
    create_test_epub(output)
