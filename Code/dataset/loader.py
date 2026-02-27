"""Benchmark CSV loader and result persistence for DPIaC-Eval.

This module is the only place that reads the input CSV, drives the generator
over the requested row slice, and writes the per-row result CSV.
"""
import os

import pandas as pd

from pipeline.iterative_generator import IterativeTemplateGenerator
from config import CONVERSATION_HISTORY_PATH, ERROR_TRACKING_DIR


def process_ioc_csv(
    input_csv: str,
    output_csv: str,
    llm_type: str,
    llm_model: str,
    start_row: int = 0,
    end_row: int | None = None,
) -> None:
    """Process a row slice of *input_csv* and save generation results to *output_csv*.

    Args:
        input_csv:  Path to the DPIaC-Eval benchmark CSV
                    (columns: ``prompt``, ``ground_truth_path``).
        output_csv: Destination path for the per-row results CSV.
        llm_type:   LLM provider string (``gemini``, ``gpt``, ``claude``, ``deepseek``).
        llm_model:  Provider model identifier.
        start_row:  First row index to process (inclusive).
        end_row:    Last row index to process (exclusive).  Defaults to all rows.
    """
    generator = IterativeTemplateGenerator(llm_type, llm_model)
    df = pd.read_csv(input_csv, encoding="latin-1")

    end_row = len(df) if end_row is None else min(end_row, len(df))
    if start_row >= end_row:
        raise ValueError(
            f"Invalid row range: start_row ({start_row}) must be less than end_row ({end_row})"
        )

    print(f"Processing rows {start_row}–{end_row - 1} ({end_row - start_row} total)")

    results: list[dict] = []
    last_index = start_row
    try:
        for index, row in df.iloc[start_row:end_row].iterrows():
            last_index = index
            result = generator.process_template(row["prompt"], row["ground_truth_path"], index)
            results.append(_build_result_row(index, row, result))
            generator.save_conversation_history(
                result["conversation_history"], CONVERSATION_HISTORY_PATH, result["success"], index
            )
    except Exception as exc:  # noqa: BLE001
        print(f"Failed at row {last_index}. Reason: {exc}")
    finally:
        _save_results(output_csv, results)
        _save_error_tracking(generator, llm_model)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_result_row(index: int, row: pd.Series, result: dict) -> dict:
    """Flatten a process_template() result into a flat CSV-ready dict."""
    return {
        "row_number": index,
        "prompt": row["prompt"],
        "ground_truth_path": row["ground_truth_path"],
        "final_template_path": result.get("template_path"),
        "success": result["success"],
        "failure_reason": result.get("reason"),
        "error_message": result.get("error"),
        "failed_at_stage": result.get("failed_stage") if not result["success"] else None,
        "total_iterations": result.get("iterations"),
        "highest_feedback_level": result.get("highest_feedback_level"),
        "coverage_percentage": result.get("coverage_percentage"),
        "accuracy_percentage": result.get("accuracy_percentage"),
    }


def _save_results(output_csv: str, results: list[dict]) -> None:
    """Append *results* to *output_csv*, creating the file if needed."""
    if not results:
        return
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    new_df = pd.DataFrame(results)
    if os.path.exists(output_csv):
        new_df = pd.concat([pd.read_csv(output_csv), new_df], ignore_index=True)
    new_df.to_csv(output_csv, index=False)


def _save_error_tracking(generator: IterativeTemplateGenerator, llm_model: str) -> None:
    """Flush the generator's error tracker buffer to a per-model CSV."""
    error_csv = os.path.join(ERROR_TRACKING_DIR, f"{llm_model}_error_history.csv")
    generator.error_tracker.save(error_csv)
