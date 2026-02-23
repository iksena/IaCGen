"""Per-run error record collector and CSV exporter.

Unlike the original class-level ``error_history`` list, ``ErrorTracker`` is
instance-scoped, which means each run gets its own clean record buffer and
there is no risk of cross-contamination between runs in the same process.
"""
import os
from datetime import datetime

import pandas as pd

from config import (
    YAML_STAGE,
    SYNTAX_STAGE,
    DEPLOYMENT_STAGE,
    FEEDBACK_LEVELS,
    SIMPLE_LEVEL_MAX_ITERATIONS,
    MODERATE_LEVEL_MAX_ITERATIONS,
)


class ErrorTracker:
    """Accumulates per-iteration error records and writes them to CSV."""

    def __init__(self, llm_type: str, llm_model: str) -> None:
        self.llm_type = llm_type
        self.llm_model = llm_model
        self._records: list[dict] = []

    def add(
        self,
        template_path: str,
        row_number: int,
        iteration_number: int,
        error_result: dict,
        stage_attempt_count: int,
    ) -> None:
        """Append one or more error records from a failed evaluation.

        Deployment errors that return a list each become a separate row;
        syntax errors are also expanded per resource.
        """
        stage = error_result["stage"]
        error = error_result["error"]

        base = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "llm_type": self.llm_type,
            "llm_model": self.llm_model,
            "template_path": template_path,
            "row_number": row_number,
            "iteration_number": iteration_number,
            "error_stage": stage,
            "stage_attempt_count": stage_attempt_count,
            "next_feedback_level": self._feedback_level(stage_attempt_count),
        }

        if stage == YAML_STAGE:
            self._records.append({**base, "error_message": str(error), "resource_name": "N/A"})

        elif stage == SYNTAX_STAGE:
            for err in error:
                self._records.append({**base, "error_message": err["message"], "resource_name": err["resource"]})

        elif stage == DEPLOYMENT_STAGE:
            if isinstance(error, list):
                for err in error:
                    self._records.append({**base, "error_message": err["reason"], "resource_name": err["resource"]})
            else:
                self._records.append({**base, "error_message": str(error), "resource_name": "N/A"})

    def save(self, output_path: str) -> str | None:
        """Write buffered records to *output_path* (appends if file exists).

        Clears the internal buffer after saving.
        Returns the output path on success, or ``None`` if there is nothing
        to write.
        """
        if not self._records:
            print("No errors to record.")
            return None

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        new_df = pd.DataFrame(self._records)

        if os.path.exists(output_path):
            combined = pd.concat([pd.read_csv(output_path), new_df], ignore_index=True)
        else:
            combined = new_df

        combined.to_csv(output_path, index=False)
        self._records.clear()
        return output_path

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _feedback_level(stage_attempt_count: int) -> str:
        if stage_attempt_count < SIMPLE_LEVEL_MAX_ITERATIONS:
            return FEEDBACK_LEVELS[0]
        if stage_attempt_count < SIMPLE_LEVEL_MAX_ITERATIONS + MODERATE_LEVEL_MAX_ITERATIONS:
            return FEEDBACK_LEVELS[1]
        return FEEDBACK_LEVELS[2]
