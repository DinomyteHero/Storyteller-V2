import argparse

from storyteller.commands.registry import COMMAND_MODULES, register_all


def test_registry_registers_expected_commands() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")

    register_all(sub)

    registered = set(sub.choices.keys())
    expected = {
        "doctor",
        "setup",
        "dev",
        "ingest",
        "query",
        "extract-knowledge",
        "organize-ingest",
        "models",
        "style-audit",
        "build-style-pack",
        "generate-era-content",
    }
    assert registered == expected


def test_registry_module_list_is_unique_and_stable() -> None:
    assert len(COMMAND_MODULES) == len(set(COMMAND_MODULES))
    assert COMMAND_MODULES[0] == "doctor"
    assert COMMAND_MODULES[-1] == "generate_era_content"
