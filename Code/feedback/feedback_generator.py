"""Progressive feedback generation for the IaCGen iterative loop.

Feedback escalates through three levels as the same stage is retried:

- **simple**   – names the failing stage only (mirrors a CI/CD status badge).
- **moderate** – includes the full error message returned by the validator.
- **advanced** – prints the template excerpt and prompts a human for guidance.
"""
from config import (
    YAML_STAGE,
    SYNTAX_STAGE,
    DEPLOYMENT_STAGE,
    SIMPLE_LEVEL_MAX_ITERATIONS,
    MODERATE_LEVEL_MAX_ITERATIONS,
    FEEDBACK_LEVELS,
    TEMPLATE_SHOWN_CHARACTERS,
)


class FeedbackGenerator:
    """Generates one feedback message per failed iteration."""

    def generate(
        self, evaluation_result: dict, stage_attempt_count: int, template_path: str
    ) -> tuple[str, str]:
        """Return *(feedback_text, feedback_level)* for a failed evaluation.

        Args:
            evaluation_result:   Dict returned by the evaluation pipeline;
                                 must contain keys ``"stage"`` and ``"error"``.
            stage_attempt_count: How many times this stage has already failed.
            template_path:       Path to the last generated template (used in
                                 advanced mode to show its content).
        """
        level = self._determine_level(stage_attempt_count)
        stage = evaluation_result["stage"]
        error = evaluation_result["error"]

        if level == "simple":
            return self._simple(stage), level
        if level == "moderate":
            return self._moderate(stage, error), level
        return self._advanced(stage, error, template_path), level

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _determine_level(stage_attempt_count: int) -> str:
        if stage_attempt_count < SIMPLE_LEVEL_MAX_ITERATIONS:
            return FEEDBACK_LEVELS[0]
        if stage_attempt_count < SIMPLE_LEVEL_MAX_ITERATIONS + MODERATE_LEVEL_MAX_ITERATIONS:
            return FEEDBACK_LEVELS[1]
        return FEEDBACK_LEVELS[2]

    @staticmethod
    def _simple(stage: str) -> str:
        labels = {
            YAML_STAGE: "YAML Syntax Errors",
            SYNTAX_STAGE: "CloudFormation Template Syntax Errors",
            DEPLOYMENT_STAGE: "Deployment Errors",
        }
        return f"\nBased on the evaluation, the template contains {labels.get(stage, stage + ' Errors')}.\n"

    @staticmethod
    def _moderate(stage: str, error) -> str:
        lines = [f"\nBased on the evaluation, the template failed at the {stage} stage. "
                 "Check below for the error details.\n"]

        if stage == YAML_STAGE:
            lines.append(f"YAML Syntax Error: {error}")

        elif stage == SYNTAX_STAGE:
            lines.append("CloudFormation Template Syntax Errors:")
            for err in error:
                lines.append(f"- Resource: {err['resource']}\n  Error: {err['message']}")

        elif stage == DEPLOYMENT_STAGE:
            if isinstance(error, list):
                lines.append("AWS Deployment Failures:")
                lines.extend(str(fail) for fail in error)
            else:
                lines.append(f"Deployment Error: {error}")

        return "\n".join(lines) + "\n"

    @staticmethod
    def _advanced(stage: str, error, template_path: str) -> str:
        """Print full context and prompt the operator for manual guidance."""
        sep = "=" * 80
        print(f"\n{sep}\nADVANCED FEEDBACK SESSION\n{sep}")
        print(f"\n1. Failed Stage: {stage}\n" + "-" * 40)

        # Show template excerpt
        print("\n2. Generated Template:\n" + "-" * 40)
        try:
            with open(template_path) as fh:
                content = fh.read()
            print(content[:TEMPLATE_SHOWN_CHARACTERS])
            if len(content) > TEMPLATE_SHOWN_CHARACTERS:
                print("... (template truncated)")
        except OSError as exc:
            print(f"Could not read template: {exc}")

        # Show error details
        print("\n3. Error Details:\n" + "-" * 40)
        if stage == YAML_STAGE:
            print(f"YAML Syntax Error: {error}")
        elif stage == SYNTAX_STAGE:
            print("CloudFormation Template Syntax Errors:")
            for err in error:
                print(f"- Resource: {err['resource']}\n  Error: {err['message']}")
        elif stage == DEPLOYMENT_STAGE:
            if isinstance(error, list):
                print("AWS Deployment Failures:")
                for fail in error:
                    print(fail)
            else:
                print(f"Deployment Error: {error}")

        # Collect human input
        print("\n4. Human Feedback Session:\n" + "-" * 40)
        print("Please provide feedback (press Enter twice to finish):")
        lines: list[str] = []
        while True:
            line = input()
            if not line.strip():
                break
            lines.append(line)
        return "\n".join(lines)
