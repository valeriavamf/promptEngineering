"""
CLI entry point for the Clean Code Bot.

Usage:
    python -m clean_code_bot <input_file> [OPTIONS]

Examples:
    python -m clean_code_bot my_script.py
    python -m clean_code_bot app.js --provider groq --output app_clean.js
    python -m clean_code_bot service.py --provider openai --model gpt-4o
"""

import os
import re  # Issue 10: moved from inside _extract_code_block to module level
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from clean_code_bot.llm import LLMClient, LLMConfig, Provider
from clean_code_bot.prompts import build_prompt
from clean_code_bot.security import sanitize_code, validate_file

load_dotenv()

# Map file extensions to human-readable language names used in prompts
_EXT_TO_LANGUAGE: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "JavaScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
    ".go": "Go",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".rs": "Rust",
}

# Pre-compiled once at import time (module-level, not inside the helper)
_FENCE_PATTERN = re.compile(r"```(?:[a-zA-Z+#]*)?\n(.*?)```", re.DOTALL)


@click.command()
@click.argument("input_file", type=click.Path(exists=False))
@click.option(
    "--provider",
    type=click.Choice(["openai", "groq"], case_sensitive=False),
    default="groq",
    show_default=True,
    help="LLM provider to use.",
)
@click.option(
    "--model",
    default="",
    help="Model override. Defaults to llama-3.3-70b-versatile (Groq) or gpt-4o-mini (OpenAI).",
)
@click.option(
    "--output",
    default="",
    help="Output file path. Defaults to <input_stem>_clean<ext> in the same directory.",
)
@click.option(
    "--temperature",
    default=0.2,
    show_default=True,
    type=float,
    help="Sampling temperature (0=deterministic, 1=creative).",
)
@click.option(
    "--max-tokens",
    default=8192,
    show_default=True,
    type=int,
    help="Maximum tokens in the model response. 8192 is the recommended minimum for 6-step CoT output.",
)
@click.option(
    "--show-reasoning",
    is_flag=True,
    default=False,
    help="Print the full CoT reasoning to stdout alongside the refactored file.",
)
def main(
    input_file: str,
    provider: str,
    model: str,
    output: str,
    temperature: float,
    max_tokens: int,
    show_reasoning: bool,
) -> None:
    """
    Refactor a code file using AI + Chain-of-Thought reasoning.

    INPUT_FILE is the path to the source file you want to clean up.
    """
    # Issue 4: resolve credentials here (thin CLI adapter) then delegate
    try:
        source_path = validate_file(input_file)
    except ValueError as exc:
        click.echo(click.style(f"[ERROR] {exc}", fg="red"), err=True)
        sys.exit(1)

    chosen_provider = Provider(provider.lower())
    env_key = "OPENAI_API_KEY" if chosen_provider == Provider.OPENAI else "GROQ_API_KEY"
    api_key = os.getenv(env_key, "")

    if not api_key:
        click.echo(
            click.style(
                f"[ERROR] Environment variable {env_key} is not set. "
                "Add it to your .env file or export it in your shell.",
                fg="red",
            ),
            err=True,
        )
        sys.exit(1)

    config = LLMConfig(
        provider=chosen_provider,
        api_key=api_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    language = _EXT_TO_LANGUAGE.get(source_path.suffix.lower(), "code")
    out_path = Path(output) if output else _default_output_path(source_path)

    click.echo(
        click.style(
            f"Sending {language} file to {chosen_provider.value} ({config.model})...",
            fg="cyan",
        )
    )

    try:
        # Issue 4: orchestration delegated to run_pipeline
        response = run_pipeline(source_path, config, language)
    except ValueError as exc:
        click.echo(click.style(f"[SECURITY] {exc}", fg="red"), err=True)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        click.echo(click.style(f"[ERROR] LLM call failed: {exc}", fg="red"), err=True)
        sys.exit(1)

    refactored = _extract_code_block(response, source_path.suffix)
    out_path.write_text(refactored, encoding="utf-8")

    click.echo(click.style(f"Refactored file written to: {out_path}", fg="green"))

    if show_reasoning:
        click.echo("\n" + click.style("-- CoT Reasoning --", fg="yellow"))
        click.echo(response)


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run_pipeline(source_path: Path, config: LLMConfig, language: str) -> str:
    """
    Orchestrate the full refactoring pipeline for a single source file.

    Steps performed:
    1. Read the source file from disk.
    2. Sanitize the raw content against prompt-injection attacks.
    3. Build the system and user prompts.
    4. Send the prompts to the configured LLM and return the raw response.

    Args:
        source_path: Validated ``Path`` to the source file.
        config: ``LLMConfig`` specifying provider, credentials, and model.
        language: Human-readable language name used inside the prompt
            (e.g. ``'Python'``, ``'TypeScript'``).

    Returns:
        The raw text response from the LLM, including CoT reasoning and
        the fenced refactored code block.

    Raises:
        ValueError: If the source file contains prompt-injection patterns.
        openai.OpenAIError: On any API-level error from the LLM provider.
    """
    raw_code = source_path.read_text(encoding="utf-8")
    clean_code = sanitize_code(raw_code)

    system_prompt, user_prompt = build_prompt(clean_code, language)

    client = LLMClient(config)
    return client.complete(system_prompt, user_prompt)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _default_output_path(source: Path) -> Path:
    """
    Derive the default output path from the source file's location.

    The output file is placed in the same directory as the source, with
    ``_clean`` appended to the stem (e.g. ``service.py`` -> ``service_clean.py``).

    Args:
        source: ``Path`` to the original source file.

    Returns:
        A new ``Path`` with the ``_clean`` suffix inserted before the
        file extension.
    """
    return source.with_name(f"{source.stem}_clean{source.suffix}")


def _extract_code_block(response: str, extension: str) -> str:
    """
    Extract the refactored code from the model's fenced code block.

    The model is instructed to return a fenced code block in Step 3.
    If no fence is found, the full response is returned as-is so no
    content is silently lost.

    Args:
        response: Full text response from the LLM.
        extension: File extension of the original source (e.g. ``'.py'``).
            Currently unused but retained for future language-specific
            parsing logic.

    Returns:
        The stripped content of the last fenced code block in the response,
        or the entire stripped response when no fence markers are present.
    """
    matches = _FENCE_PATTERN.findall(response)

    if matches:
        # The model emits CoT reasoning first and the code block last
        return matches[-1].strip()

    return response.strip()


if __name__ == "__main__":
    main()
