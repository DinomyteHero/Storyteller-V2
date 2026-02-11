import fitz  # pymupdf
import sys
from pathlib import Path

def extract_content(pdf_path: Path, keywords: list[str]) -> str:
    """Extract text from pages that likely contain the keywords."""
    print(f"Scanning {pdf_path.name}...")
    try:
        doc = fitz.open(pdf_path)
        extracted = []
        
        for i, page in enumerate(doc):
            text = page.get_text()
            # Simple heuristic: if a page mentions a keyword in the first 200 chars (header) or has high density
            header = text[:200].lower()
            if any(k.lower() in header for k in keywords):
                extracted.append(f"\n--- Page {i+1} ---\n{text}")
        
        doc.close()
        return "\n".join(extracted)
    except Exception as e:
        return f"Error reading {pdf_path.name}: {e}"

def main():
    source_dir = Path("data/lore/sourcebooks/Sourcebooks")
    
    # Define tasks: (filename_glob, keywords, output_file)
    tasks = [
        ("SW5e - Scum*.pdf", ["Factions", "Criminal", "Syndicate", "Bestiary", "Archetypes"], "temp_extraction/scum_data.txt"),
        ("SW5e - Wretched*.pdf", ["Locations", "Planets", "Settlements", "Downtime"], "temp_extraction/wretched_data.txt"),
        ("Galaxy of Intrigue.pdf", ["Factions", "Planets", "Conspiracies"], "temp_extraction/intrigue_data.txt"),
        ("The Unknown Regions.pdf", ["Planets", "Species", "Threats"], "temp_extraction/unknown_regions_data.txt"),
    ]
    
    output_dir = Path("temp_extraction")
    output_dir.mkdir(exist_ok=True)
    
    for glob_pattern, keywords, out_name in tasks:
        found_files = list(source_dir.glob(glob_pattern))
        if not found_files:
            print(f"No file matching {glob_pattern}")
            continue
            
        # Process the first match (usually unique)
        pdf_path = found_files[0]
        content = extract_content(pdf_path, keywords)
        
        # Fallback: if keywords extraction yields too little, dump TOC or first 20 pages
        if len(content) < 1000:
             print(f"  (Low yield for keywords {keywords}, dumping first 20 pages...)")
             doc = fitz.open(pdf_path)
             content = ""
             for i in range(min(20, doc.page_count)):
                 content += doc[i].get_text()
        
        out_path = Path(out_name)
        out_path.write_text(content, encoding="utf-8")
        print(f"Extracted data written to {out_path}")

if __name__ == "__main__":
    main()
