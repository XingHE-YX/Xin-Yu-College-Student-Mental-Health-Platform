"""CLI utilities for validating question-bank seed files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from src.schemas.question_bank_seed import QuestionBankSeedFile

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SEED_DIRECTORY = REPO_ROOT / "appendices" / "question_bank"


def load_seed_file(path: Path) -> QuestionBankSeedFile:
    """Load and validate one seed JSON file."""
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    return QuestionBankSeedFile.model_validate(payload)


def discover_seed_files(directory: Path) -> list[Path]:
    """Return all seed JSON files within the target directory."""
    return sorted(path for path in directory.glob("*.json") if path.is_file())


def validate_seed_files(paths: list[Path]) -> list[QuestionBankSeedFile]:
    """Validate a sequence of seed files and return their parsed models."""
    return [load_seed_file(path) for path in paths]


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for local seed validation."""
    parser = argparse.ArgumentParser(
        description="Validate questionnaire seed files under appendices/question_bank.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help=(
            "Specific seed files or directories to validate. "
            "Defaults to appendices/question_bank."
        ),
    )
    return parser


def resolve_input_paths(raw_paths: list[str]) -> list[Path]:
    """Resolve CLI inputs into concrete JSON seed-file paths."""
    if not raw_paths:
        return discover_seed_files(DEFAULT_SEED_DIRECTORY)

    resolved_paths: list[Path] = []
    for raw_path in raw_paths:
        path = Path(raw_path).resolve()
        if path.is_dir():
            resolved_paths.extend(discover_seed_files(path))
            continue
        resolved_paths.append(path)
    return sorted(dict.fromkeys(resolved_paths))


def main(argv: list[str] | None = None) -> int:
    """Run seed validation from the command line."""
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    seed_paths = resolve_input_paths(args.paths)

    if not seed_paths:
        print(f"No question-bank seed JSON files found under {DEFAULT_SEED_DIRECTORY}.")
        return 0

    has_errors = False
    for path in seed_paths:
        try:
            seed_file = load_seed_file(path)
        except FileNotFoundError:
            has_errors = True
            print(f"[ERROR] Missing file: {path}", file=sys.stderr)
        except json.JSONDecodeError as exc:
            has_errors = True
            print(f"[ERROR] Invalid JSON in {path}: {exc}", file=sys.stderr)
        except ValidationError as exc:
            has_errors = True
            print(f"[ERROR] Schema validation failed for {path}:", file=sys.stderr)
            for error in exc.errors():
                location = ".".join(str(item) for item in error["loc"])
                print(f"  - {location}: {error['msg']}", file=sys.stderr)
        else:
            print(
                f"[OK] {path} -> {seed_file.template.code} ({len(seed_file.questions)} questions)"
            )

    return 1 if has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
