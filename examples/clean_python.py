"""
Sales report generation pipeline.

Separates data loading, aggregation, serialisation, and display into
distinct, single-responsibility components following the SOLID principles.

Chain-of-Thought refactoring highlights:
- Step 2 (SOLID): ``Report`` violated SRP — it loaded, processed, saved, AND
  displayed.  Split into ``SaleLoader``, ``Aggregator``, ``ReportWriter``, and
  ``run_pipeline``.
- Step 2 (DIP): ``ReportWriter.write`` now dispatches on extension via a
  private dict of callables instead of an open-coded ``if/elif`` chain —
  adding a new format requires no changes to existing methods (OCP).
- Step 4 (smells): Broad ``except: pass`` blocks swallowed all exceptions
  silently; replaced with specific exception types and raised to the caller.
- Step 3 (naming): ``type`` → ``AggregationMode`` enum; ``r``, ``f``, ``out``
  → descriptive names throughout.
- Step 4 (magic numbers): ``1 / 2 / 3`` mode ints → ``AggregationMode`` enum
  members; date format string extracted to ``_DATE_FORMAT``.
"""

import csv
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


_DATE_FORMAT = "%Y-%m-%d"


class AggregationMode(Enum):
    """Determines how the numeric result for a report period is computed."""

    SUM = 1
    AVERAGE = 2
    MAXIMUM = 3


@dataclass
class SaleRecord:
    """A single transaction record loaded from the source file.

    Attributes:
        date: Transaction date.
        amount: Positive monetary value of the transaction.
        product: Product identifier string.
    """

    date: datetime
    amount: float
    product: str


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

class SaleLoader:
    """Reads and filters sale records from a JSON source file."""

    def load(
        self,
        source_path: Path,
        start_date: datetime,
        end_date: datetime,
    ) -> list[SaleRecord]:
        """Load transactions that fall within the given date range.

        Only records with a positive ``amount`` are included.

        Args:
            source_path: Path to the JSON file containing raw sale dicts.
            start_date: Inclusive lower bound of the date filter.
            end_date: Inclusive upper bound of the date filter.

        Returns:
            List of ``SaleRecord`` instances that pass the date and amount
            filters, in the order they appear in the source file.

        Raises:
            FileNotFoundError: If ``source_path`` does not exist.
            json.JSONDecodeError: If the file is not valid JSON.
            KeyError: If a record is missing required fields.
            ValueError: If a ``date`` field cannot be parsed.
        """
        raw: list[dict] = json.loads(source_path.read_text(encoding="utf-8"))
        records: list[SaleRecord] = []

        for entry in raw:
            record_date = datetime.strptime(entry["date"], _DATE_FORMAT)
            if start_date <= record_date <= end_date and entry["amount"] > 0:
                records.append(
                    SaleRecord(
                        date=record_date,
                        amount=float(entry["amount"]),
                        product=entry["product"],
                    )
                )

        return records


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

class Aggregator:
    """Computes a single numeric summary over a list of sale records."""

    def compute(self, records: list[SaleRecord], mode: AggregationMode) -> float:
        """Aggregate ``records`` according to ``mode``.

        Args:
            records: Non-empty list of ``SaleRecord`` instances.
            mode: Which aggregation strategy to apply.

        Returns:
            The computed aggregate value. Returns ``0.0`` when ``records``
            is empty and ``mode`` is ``AVERAGE`` or ``MAXIMUM``.

        Raises:
            ValueError: If ``mode`` is not a recognised ``AggregationMode``.
        """
        amounts = [record.amount for record in records]

        if mode is AggregationMode.SUM:
            return sum(amounts)
        if mode is AggregationMode.AVERAGE:
            return sum(amounts) / len(amounts) if amounts else 0.0
        if mode is AggregationMode.MAXIMUM:
            return max(amounts) if amounts else 0.0

        raise ValueError(f"Unrecognised aggregation mode: {mode!r}")


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

@dataclass
class ReportPayload:
    """The complete data bundle passed to ``ReportWriter``.

    Attributes:
        result: Aggregated numeric result for the period.
        records: Individual sale records included in the computation.
    """

    result: float
    records: list[SaleRecord] = field(default_factory=list)


class ReportWriter:
    """Serialises a ``ReportPayload`` to disk in JSON or CSV format."""

    _WRITERS: dict  # populated after class definition

    def write(self, payload: ReportPayload, output_path: Path) -> None:
        """Write ``payload`` to ``output_path`` using the appropriate format.

        The format is inferred from the file extension (``.json`` or ``.csv``).

        Args:
            payload: The aggregated report data to serialise.
            output_path: Destination file path (created or overwritten).

        Raises:
            ValueError: If the file extension is not ``.json`` or ``.csv``.
            OSError: If the file cannot be written.
        """
        extension = output_path.suffix.lower()
        writer_fn = self._WRITERS.get(extension)

        if writer_fn is None:
            supported = ", ".join(sorted(self._WRITERS))
            raise ValueError(
                f"Unsupported output format '{extension}'. Supported: {supported}"
            )

        writer_fn(self, payload, output_path)

    def _write_json(self, payload: ReportPayload, path: Path) -> None:
        data = {
            "result": payload.result,
            "rows": [
                {"date": r.date.strftime(_DATE_FORMAT), "amount": r.amount, "product": r.product}
                for r in payload.records
            ],
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _write_csv(self, payload: ReportPayload, path: Path) -> None:
        with path.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=["date", "amount", "product"])
            writer.writeheader()
            for record in payload.records:
                writer.writerow(
                    {"date": record.date.strftime(_DATE_FORMAT), "amount": record.amount, "product": record.product}
                )


ReportWriter._WRITERS = {".json": ReportWriter._write_json, ".csv": ReportWriter._write_csv}


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def display_summary(
    mode: AggregationMode,
    start_date: datetime,
    end_date: datetime,
    records: list[SaleRecord],
    result: float,
) -> None:
    """Print a human-readable report summary to stdout.

    Args:
        mode: Aggregation mode used to compute ``result``.
        start_date: Start of the report period.
        end_date: End of the report period.
        records: Records that were included in the computation.
        result: The aggregated numeric result.
    """
    print("Report")
    print(f"  Mode    : {mode.name}")
    print(f"  Period  : {start_date.strftime(_DATE_FORMAT)} to {end_date.strftime(_DATE_FORMAT)}")
    print(f"  Records : {len(records)}")
    print(f"  Result  : {result:.2f}")


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run_pipeline(
    source_path: Path,
    mode: AggregationMode,
    start: str,
    end: str,
    output_path: Path,
) -> None:
    """Execute the full load → aggregate → write → display pipeline.

    Args:
        source_path: Path to the JSON file of raw sale records.
        mode: Aggregation strategy.
        start: Start date string in ``YYYY-MM-DD`` format (inclusive).
        end: End date string in ``YYYY-MM-DD`` format (inclusive).
        output_path: Destination path for the serialised report.
    """
    start_date = datetime.strptime(start, _DATE_FORMAT)
    end_date = datetime.strptime(end, _DATE_FORMAT)

    records = SaleLoader().load(source_path, start_date, end_date)
    result = Aggregator().compute(records, mode)

    ReportWriter().write(ReportPayload(result=result, records=records), output_path)
    display_summary(mode, start_date, end_date, records, result)


if __name__ == "__main__":
    if len(sys.argv) != 6:
        print(
            "Usage: python clean_python.py <source.json> <mode:1|2|3> "
            "<start:YYYY-MM-DD> <end:YYYY-MM-DD> <output.json|csv>"
        )
        sys.exit(1)

    run_pipeline(
        source_path=Path(sys.argv[1]),
        mode=AggregationMode(int(sys.argv[2])),
        start=sys.argv[3],
        end=sys.argv[4],
        output_path=Path(sys.argv[5]),
    )
