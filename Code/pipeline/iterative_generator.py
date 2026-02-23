"""Core IaCGen pipeline: iterative template generation and refinement.

This module owns the orchestration logic only.  LLM calls are handled by
``models``, feedback by ``feedback``, and validation by the existing
``evaluation`` package.  Template extraction / file I/O is kept here
because it is tightly coupled to the generation loop.
"""
import os
from datetime import datetime
from typing import List, Dict

from models import create_llm
from models.base_llm import BaseLLM
from feedback.feedback_generator import FeedbackGenerator
from feedback.error_tracker import ErrorTracker
from evaluation.cloud_evaluation import (
    yaml_syntax_validation,
    evaluate_template_with_linter,
    evaluate_template_deployment,
    analyze_resource_coverage,
)
from generation.prompts.prompt_for_cloud import TOP_PROMPT, BOTTOM_PROMPT, FORMATE_SYSTEM_PROMPT
from config import (
    YAML_STAGE,
    SYNTAX_STAGE,
    DEPLOYMENT_STAGE,
    SIMPLE_LEVEL_MAX_ITERATIONS,
    MODERATE_LEVEL_MAX_ITERATIONS,
    ADVANCED_LEVEL_MAX_ITERATIONS,
    MAX_ITERATIONS,
    OUTPUT_BASE_PATH,
    FEEDBACK_LEVELS,
    TEMPLATE_SHOWN_CHARACTERS,
)


class IterativeTemplateGenerator:
    """Orchestrates the IaCGen pipeline for a single LLM model.

    Responsibilities:
    - Build and maintain conversation history.
    - Call the LLM, extract the template, and save it to disk.
    - Run the three-stage validation pipeline.
    - Escalate feedback through simple → moderate → advanced levels.
    - Delegate error recording to :class:`~feedback.ErrorTracker`.
    """

    def __init__(self, llm_type: str, llm_model: str) -> None:
        self.llm_type = llm_type
        self.llm_model = llm_model
        self.output_base_path = OUTPUT_BASE_PATH
        self.max_iterations = MAX_ITERATIONS
        self.max_stage_attempts = (
            SIMPLE_LEVEL_MAX_ITERATIONS
            + MODERATE_LEVEL_MAX_ITERATIONS
            + ADVANCED_LEVEL_MAX_ITERATIONS
        )
        self.llm: BaseLLM = create_llm(llm_type, llm_model)
        self.feedback_generator = FeedbackGenerator()
        self.error_tracker = ErrorTracker(llm_type, llm_model)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_template(
        self, initial_prompt: str, ground_truth_path: str, row_number: int
    ) -> dict:
        """Run the full iterative generation loop for one benchmark row.

        Returns a result dict with at minimum the keys:
        ``success``, ``iterations``, ``template_path``, ``conversation_history``.
        """
        stage_error_counts = {YAML_STAGE: 0, SYNTAX_STAGE: 0, DEPLOYMENT_STAGE: 0}
        highest_feedback_level = FEEDBACK_LEVELS[0]
        conversation_history = self._init_conversation(initial_prompt)
        evaluation_result: dict = {}

        for iteration in range(1, self.max_iterations + 1):
            print(f"\nIteration {iteration}")

            template_path = self._generate_and_save(conversation_history, iteration, row_number)
            conversation_history.append({"role": "assistant", "content": self._read(template_path)})

            evaluation_result = self._evaluate(template_path, ground_truth_path)

            if evaluation_result["success"]:
                print("Template generation successful!")
                return {
                    "template_path": template_path,
                    "success": True,
                    "iterations": iteration,
                    "highest_feedback_level": highest_feedback_level if iteration > 1 else None,
                    "coverage_percentage": evaluation_result["coverage_percentage"],
                    "accuracy_percentage": evaluation_result["accuracy_percentage"],
                    "conversation_history": conversation_history,
                }

            stage = evaluation_result["stage"]
            stage_attempt = stage_error_counts[stage]

            self.error_tracker.add(template_path, row_number, iteration, evaluation_result, stage_attempt)

            if stage_attempt >= self.max_stage_attempts:
                print(f"Failed after {stage_attempt} attempts at '{stage}' stage.")
                return {
                    "template_path": template_path,
                    "success": False,
                    "reason": "max_stage_error_attempts_exceeded",
                    "error": evaluation_result["error"],
                    "failed_stage": stage,
                    "iterations": iteration,
                    "highest_feedback_level": highest_feedback_level,
                    "conversation_history": conversation_history,
                }

            feedback, feedback_level = self.feedback_generator.generate(
                evaluation_result, stage_attempt, template_path
            )
            if FEEDBACK_LEVELS.index(feedback_level) > FEEDBACK_LEVELS.index(highest_feedback_level):
                highest_feedback_level = feedback_level

            conversation_history.append({
                "role": "user",
                "content": (
                    f"The previous template had issues. Given feedback: {feedback}\n"
                    "Please generate an improved version of the template that addresses these issues."
                ),
            })
            stage_error_counts[stage] += 1

        return {
            "template_path": template_path,
            "success": False,
            "reason": "max_iterations_exceeded",
            "failed_stage": evaluation_result.get("stage"),
            "iterations": self.max_iterations,
            "highest_feedback_level": highest_feedback_level,
            "conversation_history": conversation_history,
        }

    def save_conversation_history(
        self,
        conversation_history: list,
        output_base_path: str,
        is_success: bool,
        row_number: int,
    ) -> str:
        """Persist the conversation history for one row to a plain-text file."""
        output_dir = os.path.join(output_base_path, self.llm_type, self.llm_model)
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(
            output_dir, f"conversation_row{row_number}_{is_success}_{timestamp}.txt"
        )

        with open(filename, "w", encoding="utf-8") as fh:
            fh.write(
                f"Conversation History — {self.llm_type} — "
                f"Row: {row_number} — Success: {is_success} — {timestamp}\n"
            )
            fh.write("=" * 80 + "\n\n")
            for i, msg in enumerate(conversation_history, 1):
                fh.write(f"Message {i}\nRole: {msg['role']}\n" + "-" * 40 + "\n")
                content = msg["content"]
                # Truncate long assistant templates in the log
                if msg["role"] == "assistant" and content.strip().startswith("AWSTemplateFormatVersion"):
                    content = content[:TEMPLATE_SHOWN_CHARACTERS] + "...\n"
                fh.write(content + "\n" + "=" * 80 + "\n\n")

        return filename

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _init_conversation(initial_prompt: str) -> List[Dict[str, str]]:
        """Build the opening two turns of the conversation."""
        return [
            {"role": "system", "content": FORMATE_SYSTEM_PROMPT},
            {"role": "user", "content": TOP_PROMPT + initial_prompt + BOTTOM_PROMPT},
        ]

    def _generate_and_save(
        self, conversation_history: list, iteration_num: int, row_num: int
    ) -> str:
        """Call the LLM, extract the IaC template block, and write to disk."""
        raw_content = self.llm.generate(conversation_history)
        content = self._extract_template(raw_content)

        output_dir = os.path.join(self.output_base_path, self.llm_type, self.llm_model)
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(
            output_dir, f"row_{row_num}_update_{iteration_num}_template_{timestamp}.yaml"
        )
        with open(output_file, "w") as fh:
            fh.write(content)
        return output_file

    @staticmethod
    def _extract_template(content: str) -> str:
        """Strip planning commentary and isolate the YAML template block.

        Priority order:
        1. Content between ``<iac_template>…</iac_template>`` tags.
        2. Everything from ``AWSTemplateFormatVersion`` onward (fallback).
        """
        # Remove optional planning block
        p_start = content.find("<template_planning>")
        p_end = content.find("</template_planning>", p_start)
        if p_start != -1 and p_end != -1:
            content = content[:p_start] + content[p_end + len("</template_planning>"):]

        # Extract IaC template block
        t_start = content.find("<iac_template>")
        t_end = content.find("</iac_template>", t_start)
        if t_start != -1 and t_end != -1:
            return content[t_start + len("<iac_template>"):t_end].strip()

        # Fallback: locate AWSTemplateFormatVersion header
        print("Warning: <iac_template> tags not found — falling back to AWSTemplateFormatVersion.")
        aws_pos = content.find("AWSTemplateFormatVersion")
        if aws_pos != -1:
            content = content[aws_pos:].strip()
            backtick_pos = content.find("```")
            if backtick_pos != -1:
                content = content[:backtick_pos].strip()
            return content

        print("Warning: AWSTemplateFormatVersion not found in LLM output.")
        return content

    def _evaluate(self, template_path: str, ground_truth_path: str) -> dict:
        """Run all validation stages and return a structured result dict."""
        yaml_valid, yaml_error = yaml_syntax_validation(template_path)
        if not yaml_valid:
            return {"success": False, "stage": YAML_STAGE, "error": yaml_error}

        syntax_result = evaluate_template_with_linter(template_path)
        if not syntax_result["passed"]:
            return {"success": False, "stage": SYNTAX_STAGE, "error": syntax_result["error_details"]}

        deploy_result = evaluate_template_deployment(template_path)
        if not deploy_result["success"]:
            return {"success": False, "stage": DEPLOYMENT_STAGE, "error": deploy_result["failed_reason"]}

        coverage = analyze_resource_coverage(ground_truth_path, template_path)
        return {
            "success": True,
            "correct_resources": coverage["correct_resources"],
            "missing_resources": coverage["missing_resources"],
            "extra_resources": coverage["extra_resources"],
            "coverage_percentage": coverage["coverage_percentage"],
            "accuracy_percentage": coverage["accuracy_percentage"],
        }

    @staticmethod
    def _read(path: str) -> str:
        with open(path) as fh:
            return fh.read()
