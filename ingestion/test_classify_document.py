"""Unit tests for document classifier: heuristic-first auto-tagging."""
import unittest
from pathlib import Path

from ingestion.classify_document import classify_document
from shared.lore_metadata import (
    DOC_TYPE_NOVEL,
    DOC_TYPE_SOURCEBOOK,
    DOC_TYPE_ADVENTURE,
    DOC_TYPE_MAP,
    DOC_TYPE_UNKNOWN,
    SECTION_KIND_GEAR,
    SECTION_KIND_HOOK,
    SECTION_KIND_FACTION,
    SECTION_KIND_LOCATION,
    SECTION_KIND_LORE,
    SECTION_KIND_UNKNOWN,
)


class TestDocTypeFromPath(unittest.TestCase):
    """Heuristic doc_type from path/filename."""

    def test_novel_folder(self) -> None:
        """Folder contains 'novel' -> doc_type=novel."""
        p = Path("books/novel/something.txt")
        r = classify_document(p, None, None)
        self.assertEqual(r["doc_type"], DOC_TYPE_NOVEL)

    def test_sourcebook_filename(self) -> None:
        """Filename contains sourcebook -> doc_type=sourcebook."""
        p = Path("/data/core_rulebook_sourcebook.pdf")
        r = classify_document(p, None, None)
        self.assertEqual(r["doc_type"], DOC_TYPE_SOURCEBOOK)

    def test_adventure_filename(self) -> None:
        """Filename contains adventure -> doc_type=adventure."""
        p = Path("modules/the_adventure_module.epub")
        r = classify_document(p, None, None)
        self.assertEqual(r["doc_type"], DOC_TYPE_ADVENTURE)

    def test_map_filename(self) -> None:
        """Filename contains map -> doc_type=map."""
        p = Path("maps/sector_atlas.pdf")
        r = classify_document(p, None, None)
        self.assertEqual(r["doc_type"], DOC_TYPE_MAP)

    def test_unknown_path(self) -> None:
        """No matching path -> doc_type=unknown."""
        p = Path("misc/random_file.txt")
        r = classify_document(p, None, None)
        self.assertEqual(r["doc_type"], DOC_TYPE_UNKNOWN)


class TestSectionKindFromText(unittest.TestCase):
    """Heuristic section_kind from text headings."""

    def test_gear_heading(self) -> None:
        """Headings like Equipment, Gear, Weapons -> section_kind=gear."""
        text = "## Equipment\nBlaster rifles, vibroblades..."
        r = classify_document(Path("x.txt"), text, None)
        self.assertEqual(r["section_kind_guess"], SECTION_KIND_GEAR)

    def test_hook_heading(self) -> None:
        """Adventure Summary, Act I, Encounter -> section_kind=hook."""
        text = "Adventure Summary\nYou arrive at the spaceport..."
        r = classify_document(Path("x.txt"), text, None)
        self.assertEqual(r["section_kind_guess"], SECTION_KIND_HOOK)

    def test_faction_heading(self) -> None:
        """Faction, Organizations -> section_kind=faction."""
        text = "Faction: The Empire\nOrganizations allied..."
        r = classify_document(Path("x.txt"), text, None)
        self.assertEqual(r["section_kind_guess"], SECTION_KIND_FACTION)

    def test_location_heading(self) -> None:
        """Planet, Location, Regions -> section_kind=location."""
        text = "Planet: Tatooine\nLocation: Mos Eisley..."
        r = classify_document(Path("x.txt"), text, None)
        self.assertEqual(r["section_kind_guess"], SECTION_KIND_LOCATION)

    def test_chapter_narrative(self) -> None:
        """Chapter + narrative prose -> section_kind=lore."""
        text = "Chapter 3\nLuke said hello. Leia asked a question."
        r = classify_document(Path("x.txt"), text, None)
        self.assertEqual(r["section_kind_guess"], SECTION_KIND_LORE)

    def test_empty_text(self) -> None:
        """Empty text -> section_kind=unknown."""
        r = classify_document(Path("x.txt"), None, None)
        self.assertEqual(r["section_kind_guess"], SECTION_KIND_UNKNOWN)


class TestEraDetection(unittest.TestCase):
    """Era from path or default."""

    def test_default_era_preferred(self) -> None:
        """CLI default era overrides path inference."""
        r = classify_document(Path("random.txt"), "", "LOTF")
        self.assertEqual(r["era"], "LOTF")

    def test_era_from_path(self) -> None:
        """Path contains lotf -> era=LOTF."""
        r = classify_document(Path("lotf/novels/book.txt"), "", None)
        self.assertEqual(r["era"], "LOTF")

    def test_era_from_path_old_republic(self) -> None:
        """Path contains old_republic -> era=Old Republic."""
        r = classify_document(Path("old_republic/something.txt"), "", None)
        self.assertEqual(r["era"], "Old Republic")

    def test_era_from_alias_folder(self) -> None:
        """Folder alias (Before the Republic) -> era=Old Republic."""
        r = classify_document(Path("Before the Republic/novels/book.txt"), "", None)
        self.assertEqual(r["era"], "Old Republic")

    def test_era_from_alias_folder_legacy(self) -> None:
        """Folder alias (Legacy Era) -> era=LOTF."""
        r = classify_document(Path("Legacy Era/novels/book.txt"), "", None)
        self.assertEqual(r["era"], "LOTF")

    def test_era_from_folder_variants(self) -> None:
        """Folder variants map to legacy labels without aliases file."""
        r = classify_document(Path("Rebellion Era/novels/book.txt"), "", None)
        self.assertEqual(r["era"], "Rebellion")
        r = classify_document(Path("New Republic Era/novels/book.txt"), "", None)
        self.assertEqual(r["era"], "New Republic")
        r = classify_document(Path("Old Galactic Republic Era/novels/book.txt"), "", None)
        self.assertEqual(r["era"], "Old Republic")

    def test_era_unknown_when_no_hints(self) -> None:
        """No path hints and no default -> era=None."""
        r = classify_document(Path("misc/xyz.txt"), "", None)
        self.assertIsNone(r["era"])


class TestClassificationResult(unittest.TestCase):
    """Full classification output shape."""

    def test_result_keys(self) -> None:
        """Result has doc_type, era, section_kind_guess, confidence, signals_used."""
        r = classify_document(Path("sourcebook.pdf"), "Equipment: blasters.", "LOTF")
        self.assertIn("doc_type", r)
        self.assertIn("era", r)
        self.assertIn("section_kind_guess", r)
        self.assertIn("confidence", r)
        self.assertIn("signals_used", r)

    def test_heuristics_tag_majority(self) -> None:
        """At least 80% of test inputs get heuristic classification."""
        test_cases = [
            (Path("novels/book.txt"), ""),
            (Path("sourcebook.pdf"), "Equipment: items."),
            (Path("adventure_module.epub"), "Adventure Summary: ..."),
            (Path("sector_map.pdf"), ""),
            (Path("lotf/story.txt"), "Chapter 1\nLuke said hi."),
            (Path("rulebook.pdf"), "Weapons: blasters."),
            (Path("factions.txt"), "Faction: Empire"),
            (Path("locations.txt"), "Planet: Tatooine"),
            (Path("random.txt"), "random content"),
            (Path("clone_wars/novel.txt"), ""),
        ]
        tagged = 0
        for path, text in test_cases:
            r = classify_document(path, text or None, None)
            if r["doc_type"] != DOC_TYPE_UNKNOWN or r["section_kind_guess"] != SECTION_KIND_UNKNOWN:
                tagged += 1
        pct = tagged / len(test_cases)
        self.assertGreaterEqual(pct, 0.8, f"Expected >=80% heuristic tag, got {pct:.0%}")
