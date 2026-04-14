"""
Input validation and sanitization to prevent prompt injection attacks.
"""

import re
from pathlib import Path

# frozenset: module-level constant must be immutable so callers cannot
# accidentally mutate the allowed-extension list at runtime.
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cs", ".cpp",
    ".c", ".go", ".rb", ".php", ".swift", ".kt", ".rs",
})

MAX_FILE_SIZE_BYTES = 50_000  # 50 KB

# Patterns that indicate an attempt to hijack the prompt
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"forget\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"you\s+are\s+now\s+a",
    r"act\s+as\s+(a\s+)?(?:different|new|another)",
    r"new\s+instructions?\s*:",
    r"system\s*:\s*(you|your)",
    r"<\s*system\s*>",
    r"\[INST\]",
    r"###\s*instruction",
]

_INJECTION_RE = re.compile(
    "|".join(_INJECTION_PATTERNS),
    re.IGNORECASE | re.MULTILINE,
)


def validate_file(path: str) -> Path:
    """
    Validate that the given path points to a readable code file
    within allowed size and extension constraints.

    Args:
        path: Filesystem path to the file to validate.

    Returns:
        A resolved ``pathlib.Path`` object for the validated file.

    Raises:
        ValueError: If the file does not exist, is not a regular file,
            has an unsupported extension, is empty, or exceeds the
            maximum allowed size.
    """
    p = Path(path)

    if not p.exists():
        raise ValueError(f"File not found: {path}")

    if not p.is_file():
        raise ValueError(f"Path is not a file: {path}")

    if p.suffix.lower() not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValueError(
            f"Unsupported file type '{p.suffix}'. Allowed: {allowed}"
        )

    size = p.stat().st_size
    if size == 0:
        raise ValueError("File is empty.")

    if size > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"File is too large ({size} bytes). Maximum allowed: {MAX_FILE_SIZE_BYTES} bytes."
        )

    return p


def sanitize_code(raw: str) -> str:
    """
    Sanitize raw code content before embedding it in an LLM prompt.

    Detects and rejects obvious prompt-injection attempts. Returns
    the original content unchanged when no injection is detected.

    Args:
        raw: Raw source code string read from the input file.

    Returns:
        The original ``raw`` string, unmodified, when no injection
        patterns are found.

    Raises:
        ValueError: If a prompt-injection pattern is detected in the
            input, including a short excerpt of the matched text.
    """
    match = _INJECTION_RE.search(raw)
    if match:
        matched_text = match.group(0)
        # Append ellipsis only when the matched text was truncated.
        preview = matched_text[:60]
        suffix = "..." if len(matched_text) > 60 else ""
        raise ValueError(
            f"Potential prompt injection detected in input file "
            f"(matched: '{preview}{suffix}'). Aborting."
        )
    return raw
