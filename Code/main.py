import sys
import os
import pandas as pd
import anthropic
import google.generativeai as genai
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime
from generation.cloud_generation import (
    gemini_generate_cf_template,
    chatgpt_generate_cf_template,
    claude_generate_cf_template
)
from evaluation.cloud_evaluation import (
    yaml_syntax_validation,
    evaluate_template_with_linter,
    evaluate_template_deployment,
    analyze_resource_coverage
)
from generation.prompts.prompt_for_cloud import (
    TOP_PROMPT, BOTTOM_PROMPT, FORMATE_SYSTEM_PROMPT,
    TWO_STEP_GENERATE_PROMPT, TWO_STEP_PLAN_BOTTOM, TWO_STEP_PLAN_TOP, TWO_STEP_SYSTEM_PROMPT,
    SCOT_SYSTEM_PROMPT, SCOT_PLAN_TOP, SCOT_PLAN_BOTTOM, SCOT_GENERATE_PROMPT,
    CGO_SYSTEM_PROMPT, CGO_PLAN_TOP, CGO_PLAN_BOTTOM, CGO_GENERATE_PROMPT,
)
# ADD after the existing imports, around line 20
from security import evaluate_security_stage
from checkov_context import get_checkov_policy_context


# Load environment variables from .env file
load_dotenv()

GEMIN_API_KEY = os.getenv('GEMIN_API_KEY', '')
CHATGPT_API_KEY = os.getenv('CHATGPT_API_KEY', '')
CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY', '')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', '')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')


class IterativeTemplateGenerator:
    YAML_STAGE_NAME = 'yaml_validation'
    SYNTAX_STAGE_NAME = 'syntax_validation'
    DEPLOYMENT_STAGE_NAME = 'deployment'
    # INSIDE class IterativeTemplateGenerator — add after DEPLOYMENT_STAGE_NAME (line ~41)
    SECURITY_STAGE_NAME = 'security_validation'
    SECURITY_PASS_THRESHOLD = 1.0   # proceed to deployability if ≥100% checks pass
    FEEDBACK_LEVELS = ['simple', 'moderate', 'advanced']
    TEMPLATE_SHOWN_CHARACTERS = 1000
    # Static variable to store error history across all instances
    error_history = []

    def __init__(self, llm_type, llm_model, prompt_strategy="cgo"):
        self.llm_type = llm_type
        self.llm_model = llm_model
        self.prompt_strategy = prompt_strategy
        self.simple_level_max_iterations = 0
        self.moderate_level_max_iterations = 10
        self.advance_level_max_iterations = 0
        self.max_iterations = 10
        self.max_same_error_attempts = self.simple_level_max_iterations + self.moderate_level_max_iterations + self.advance_level_max_iterations
        self.output_base_path = "llm_generated_data/template/iterative/"
        self.setup_llm_model()

    # Done
    def setup_llm_model(self):
        if self.llm_type == "gemini":
            genai.configure(api_key=GEMIN_API_KEY)
            self.model = genai.GenerativeModel(self.llm_model)
        elif self.llm_type == "gpt":
            self.model = OpenAI(api_key=CHATGPT_API_KEY)
        elif self.llm_type == "github":
            self.model = OpenAI(base_url="https://models.inference.ai.azure.com", api_key=GITHUB_TOKEN)
        elif self.llm_type == "claude":
            self.model = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        elif self.llm_type == "deepseek":
            base_url = ("https://openrouter.ai/api/v1" if "openrouter" in self.llm_model else "https://api.deepseek.com")
            self.model = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=base_url)
        elif self.llm_type == "ollama":
            self.model = OpenAI(
                api_key="ollama",
                base_url="http://localhost:11434/v1"
            )
        else:
            raise ValueError(f"Unsupported LLM type: {self.llm_type}")

    # Done
    def generate_template(self, prompt, iteration_num, row_num):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"{self.output_base_path}{self.llm_type}/{self.llm_model}/"
        
        if self.llm_type == "gemini":
            return gemini_generate_cf_template(
                self.model, 
                prompt, 
                f"{output_path}row_{row_num}_update_{iteration_num}_template_{timestamp}.yaml"
            )
        elif self.llm_type == "gpt":
            return chatgpt_generate_cf_template(
                self.model, 
                prompt, 
                f"{output_path}row_{row_num}_update_{iteration_num}_template_{timestamp}.yaml",
                self.llm_model
            )
        else:  # claude
            return claude_generate_cf_template(
                self.model, 
                prompt, 
                f"{output_path}row_{row_num}_update_{iteration_num}_template_{timestamp}.yaml",
                self.llm_model
            )

    # Done
    def evaluate_template(self, template_path, ground_truth_path):
        """
        When success is True, will return resource coverage metrics. Else, return error message and error stage.
        """
        # Step 1: YAML syntax validation
        yaml_valid, yaml_error = yaml_syntax_validation(template_path)
        if not yaml_valid:
            return {
                'success': False,
                'stage': self.YAML_STAGE_NAME,
                'error': yaml_error
            }

        # Step 2: Template syntax validation
        syntax_result = evaluate_template_with_linter(template_path)
        if not syntax_result['passed']:
            return {
                'success': False,
                'stage': self.SYNTAX_STAGE_NAME,
                # 'total_issues': syntax_result['error_count'],
                # 'severity_breakdown': syntax_result['error_by_severity'],
                'error': syntax_result['error_details']
            }

        # ── NEW: Step 2.5: Security validation (Checkov) ──────────────────────────
        security_result = evaluate_security_stage(template_path, self.SECURITY_PASS_THRESHOLD)
        if not security_result['success']:
            return {
                'success': False,
                'stage': self.SECURITY_STAGE_NAME,
                'error': security_result['error'],          # list of failed check dicts
                'pass_percentage': security_result['pass_percentage'],
                'passed_checks': security_result['passed_checks'],
                'failed_checks': security_result['failed_checks'],
                'total_checks': security_result['total_checks'],
            }
        # ── END NEW ───────────────────────────────────────────────────────────────

        # Step 3: Deployment validation
        deploy_result = evaluate_template_deployment(template_path)
        if not deploy_result['success']:
            return {
                'success': False,
                'stage': self.DEPLOYMENT_STAGE_NAME,
                'error': deploy_result['failed_reason']
            }

        # Step 4: Resource coverage analysis
        coverage_result = analyze_resource_coverage(ground_truth_path, template_path)
        return {
            'success': True,
            'correct_resources': coverage_result['correct_resources'],
            'missing_resources': coverage_result['missing_resources'],
            'extra_resources': coverage_result['extra_resources'],
            'coverage_percentage': coverage_result['coverage_percentage'],
            'accuracy_percentage': coverage_result['accuracy_percentage'],
            'security_pass_percentage': security_result['pass_percentage'],  # ← fixed: include security pass percentage in final success result
        }

    # Done
    # ToDo Support advanced level feedback
    def generate_error_feedback(self, evaluation_result, attempt_num, template_path):
        """Generate feedback based on evaluation results and attempt number. Will assume the template failed to pass one evaluation."""
        feedback_level = self.FEEDBACK_LEVELS[
            0 if attempt_num < self.simple_level_max_iterations else
            1 if attempt_num < (self.simple_level_max_iterations + self.moderate_level_max_iterations) else
            2
        ]
        
        stage = evaluation_result['stage']
        error = evaluation_result['error']

        # ── NEW: Security stage gets its own feedback path ────────────────────────
        if stage == self.SECURITY_STAGE_NAME:
            pass_pct = evaluation_result.get('pass_percentage', 0.0)
            if feedback_level == 'moderate':
                feedback = self.generate_security_simple_feedback(error, pass_pct)
            else:
                # moderate and advanced both get full policy-context feedback
                feedback = self.generate_security_remediation_feedback(error, pass_pct)
            return feedback, feedback_level
        # ── END NEW ───────────────────────────────────────────────────────────────
        
        if feedback_level == 'simple':
            feedback = self.generate_simple_level_feedback(stage, error)
        elif feedback_level == 'moderate':
            feedback = self.generate_moderate_level_feedback(stage, error)
        else:
            feedback = self.generate_advanced_level_feedback(stage, error, template_path)
        return feedback, feedback_level
    
    # Done
    def generate_simple_level_feedback(self, stage, error):
        feedback = f"\nBased on the evaluation, the template contains "

        if stage == self.YAML_STAGE_NAME:
            feedback += f"YAML Syntax Errors.\n"
        elif stage == self.SYNTAX_STAGE_NAME:
            feedback += "CloudFormation Template Syntax Errors.\n"
        elif stage == self.DEPLOYMENT_STAGE_NAME:
            # Handle single error object (like ClientError)
            feedback += f"Deployment Errors.\n"
        # Uncomment below code if you want to improve the coverage also
        # elif stage == 'coverage':
        #     feedback += "Resource Coverage Issues."
        return feedback

    # Done
    def generate_moderate_level_feedback(self, stage, error):
        feedback = f"\nBased on the evaluation, the template failed at the {stage} stage. Check below for the error details.\n"

        if stage == self.YAML_STAGE_NAME:
            feedback += f"YAML Syntax Error: {error}\n"
        elif stage == self.SYNTAX_STAGE_NAME:
            feedback += "CloudFormation Template Syntax Errors:\n"
            for err in error:
                feedback += f"- Resource: {err['resource']}\n  Error: {err['message']}\n"
        elif stage == self.DEPLOYMENT_STAGE_NAME:
            if isinstance(error, list):
                feedback += "AWS Deployment Failures:\n"
                for fail in error:
                    feedback += f"{fail}\n"
            else:
                # Handle single error object (like ClientError)
                feedback += f"Deployment Error: {str(error)}\n"
        # Uncomment below code if you want to improve the coverage also
        # elif stage == 'coverage':
        #     feedback += "Resource Coverage Issues:\n"
        #     feedback += f"- Missing Resources: {error['missing']}\n"
        #     feedback += f"- Extra Resources: {error['extra']}\n"
        return feedback

    def generate_advanced_level_feedback(self, stage, error, template_path):
        """
        Generate advanced level feedback by showing detailed error information and getting human input.
        
        Args:
            stage: The stage where the template failed
            error: The error details
            template_path: Path to the generated template
        
        Returns:
            str: Combined feedback including error details and human input
        """
        # Print detailed information about the failure
        print("\n" + "=" * 80)
        print("ADVANCED FEEDBACK SESSION")
        print("=" * 80)
        
        # Print the failed stage
        print(f"\n1. Failed Stage: {stage}")
        print("-" * 40)
        
        # Print the generated template
        print("\n2. Generated Template:")
        print("-" * 40)
        try:
            with open(template_path, 'r') as f:
                template_content = f.read()
                print(template_content[:self.TEMPLATE_SHOWN_CHARACTERS])  # Show first xx chars of the template
                if len(template_content) > self.TEMPLATE_SHOWN_CHARACTERS:
                    print("... (template truncated)")
        except Exception as e:
            print(f"Error reading template: {e}")
        
        # Print the error message
        print("\n3. Error Details:")
        print("-" * 40)
        if stage == self.YAML_STAGE_NAME:
            print(f"YAML Syntax Error: {error}")
        elif stage == self.SYNTAX_STAGE_NAME:
            print("CloudFormation Template Syntax Errors:")
            for err in error:
                print(f"- Resource: {err['resource']}")
                print(f"  Error: {err['message']}")
        elif stage == self.DEPLOYMENT_STAGE_NAME:
            if isinstance(error, list):
                print("AWS Deployment Failures:")
                for fail in error:
                    print(f"{fail}")
            else:
                print(f"Deployment Error: {str(error)}")
        
        # Get human feedback
        print("\n4. Human Feedback Session:")
        print("-" * 40)
        print("Please provide feedback for improving the template.")
        print("Consider the following aspects:")
        print("- Specific issues to address")
        print("- Suggested corrections")
        print("- Additional requirements or constraints")
        print("\nEnter your feedback (press Enter twice to finish):")
        
        # Collect multiline feedback
        feedback_lines = []
        while True:
            line = input()
            if line.strip() == "":
                break
            feedback_lines.append(line)
        
        human_feedback = "\n".join(feedback_lines)
        
        return human_feedback
    
    # ADD these two methods inside class IterativeTemplateGenerator,
    def generate_security_remediation_feedback(self, failed_checks: list[dict], pass_percentage: float) -> str:
        """
        LLMSecConfig-style security remediation feedback.
        Injects Checkov policy source code context (Stream 2) for each failed check.
        """
        policy_context = get_checkov_policy_context(failed_checks)

        feedback = (
            f"\nThe template failed the security validation stage. "
            f"Pass rate: {pass_percentage:.1f}% "
            f"(threshold: {self.SECURITY_PASS_THRESHOLD * 100:.0f}%).\n"
            f"The following Checkov security checks failed:\n"
        )
        for check in failed_checks:
            feedback += f"  - [{check['check_id']}] {check['check_name']} on resource: {check['resource']}\n"

        if policy_context:
            feedback += (
                "\n=== Security Policy Reference ===\n"
                "Use the following policy definitions and fix examples to correct each violation:\n\n"
                f"{policy_context}\n"
                "=================================\n"
            )

        feedback += "\nPlease regenerate the CloudFormation template fixing all security violations listed above.\n"
        return feedback

    def generate_security_simple_feedback(self, failed_checks: list[dict], pass_percentage: float) -> str:
        """Minimal feedback for the security stage (no policy context injected)."""
        check_ids = ", ".join(c["check_id"] for c in failed_checks)
        return (
            f"\nThe template failed the security validation stage "
            f"(pass rate: {pass_percentage:.1f}%, threshold: {self.SECURITY_PASS_THRESHOLD * 100:.0f}%). "
            f"Failed checks: {check_ids}. "
            f"Please fix the security misconfigurations.\n"
        )


    def add_error_record(self, template_path, row_number, iteration_number, error_result, stage_attempt_count):
        """
        Add error record to the static error_history.
        """
        stage = error_result['stage']
        error = error_result['error']
        
        # Base error record
        base_record = {
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'llm_type': self.llm_type,
            'llm_model': self.llm_model,
            'template_path': template_path,
            'row_number': row_number,
            'iteration_number': iteration_number,
            'error_stage': stage,
            'stage_attempt_count': stage_attempt_count,
            'next_feedback_level': self.FEEDBACK_LEVELS[
                0 if stage_attempt_count < self.simple_level_max_iterations else
                1 if stage_attempt_count < (self.simple_level_max_iterations + self.moderate_level_max_iterations) else
                2
            ],
        }
        
        # Handle different error types and add to error_history
        if stage == self.YAML_STAGE_NAME:
            record = {
                **base_record,
                'error_message': str(error),
                'resource_name': 'N/A'
            }
            self.error_history.append(record)
            
        elif stage == self.SYNTAX_STAGE_NAME:
            for err in error:
                record = {
                    **base_record,
                    'error_message': err['message'],
                    'resource_name': err['resource']
                }
                self.error_history.append(record)
                
        elif stage == self.DEPLOYMENT_STAGE_NAME:
            if isinstance(error, list):
                for err in error:
                    record = {
                        **base_record,
                        'error_message': err['reason'],
                        'resource_name': err['resource']
                    }
                    self.error_history.append(record)
            else:
                record = {
                    **base_record,
                    'error_message': str(error),
                    'resource_name': 'N/A'
                }
                self.error_history.append(record)
        # In add_error_record(), ADD a security stage branch in the if/elif chain:
        elif stage == self.SECURITY_STAGE_NAME:
            for check in error:   # error is a list of failed check dicts
                record = {
                    **base_record,
                    'error_message': f"[{check['check_id']}] {check['check_name']}",
                    'resource_name': check.get('resource', 'N/A')
                }
                self.error_history.append(record)




    def process_template(self, initial_prompt, ground_truth_path, row_number):
        stages_error_count = {self.YAML_STAGE_NAME: 0, self.SYNTAX_STAGE_NAME: 0, self.SECURITY_STAGE_NAME: 0, self.DEPLOYMENT_STAGE_NAME: 0}
        iteration = 1
        conversation_history = []
        highest_feedback_level = self.FEEDBACK_LEVELS[0]  # Start with 'simple'

        print(f"\nRow {row_number} - Generating Architecture Plan...")
        strategy_map = {
            "two_step": (TWO_STEP_SYSTEM_PROMPT, TWO_STEP_PLAN_TOP,  TWO_STEP_PLAN_BOTTOM,  TWO_STEP_GENERATE_PROMPT),
            "scot":     (SCOT_SYSTEM_PROMPT,     SCOT_PLAN_TOP,      SCOT_PLAN_BOTTOM,      SCOT_GENERATE_PROMPT),
            "cgo":      (CGO_SYSTEM_PROMPT,      CGO_PLAN_TOP,       CGO_PLAN_BOTTOM,       CGO_GENERATE_PROMPT),
        }
        sys_prompt, plan_top, plan_bottom, gen_prompt = strategy_map[self.prompt_strategy]
        
        # 1. Initialize system prompt
        conversation_history.append({
            "role": "system",
            "content": sys_prompt
        })
        
        # 2. Ask for the plan
        conversation_history.append({
            "role": "user",
            "content": plan_top + initial_prompt + plan_bottom
        })
        
        # 3. Get the plan from the LLM and add it to history
        plan_text = self.generate_plan_response(conversation_history)
        conversation_history.append({
            "role": "assistant",
            "content": plan_text
        })
        
        # --- PHASE 2: TEMPLATE GENERATION & EVALUATION LOOP ---
        # 4. Prompt the LLM to write the code based on the plan

        # Initialize conversation with system context
        # conversation_history.append({
        #     "role": "system",
        #     "content": FORMATE_SYSTEM_PROMPT
        # })
        
        # Add initial user prompt
        conversation_history.append({
            "role": "user",
            "content": gen_prompt
        })
        
        while iteration <= self.max_iterations:
            print(f"\nRow {row_number} Iteration {iteration}")
            print("Stage Error Counts:", stages_error_count)
            
            # Generate template using conversation history
            template_path = self.generate_template_with_history(
                conversation_history,
                iteration,
                row_number
            )

            # Add the generated template to conversation history
            with open(template_path, 'r') as f:
                template_content = f.read()
            
            conversation_history.append({
                "role": "assistant",
                "content": template_content
            })
            
            # Evaluate template
            evaluation_result = self.evaluate_template(template_path, ground_truth_path)
            
            if evaluation_result['success']:
                print("Template generation successful!")
                return {
                    'template_path': template_path,
                    'success': True,
                    'iterations': iteration,
                    'highest_feedback_level': highest_feedback_level if iteration > 1 else None,   # In case no feedback is given.
                    'coverage_percentage': evaluation_result['coverage_percentage'],
                    'security_pass_percentage': evaluation_result.get('security_pass_percentage'),   # only set when security stage is reached
                    'accuracy_percentage': evaluation_result['accuracy_percentage'],
                    # 'missing_resources': evaluation_result['missing_resources'],
                    # 'extra_resources': evaluation_result['extra_resources'],
                    'conversation_history': conversation_history
                }
            
            # Track stage errors
            current_stage = evaluation_result.get('stage')
            stage_attempt_count = stages_error_count.get(current_stage, 0)

           # Store error record before incrementing the counter
            if not evaluation_result['success']:
                self.add_error_record(
                    template_path,
                    row_number,
                    iteration,
                    evaluation_result,
                    stages_error_count[current_stage]
                )
                print(f"Row {row_number} Iteration {iteration} failed. Error: {self.error_history[-1]}")

            # Stop when fail too many times in a stage
            if stage_attempt_count >= (self.simple_level_max_iterations + self.moderate_level_max_iterations + self.advance_level_max_iterations):
                print(f"Failed after {stage_attempt_count} attempts in {current_stage} stage")
                return {
                    'template_path': template_path,
                    'success': False,
                    'reason': 'max_stage_error_attempts_exceeded',
                    'error': evaluation_result['error'],
                    'failed_stage': evaluation_result['stage'],
                    'iterations': iteration,
                    'highest_feedback_level': highest_feedback_level,
                    'conversation_history': conversation_history,
                    'security_pass_percentage': evaluation_result.get('pass_percentage', None) if evaluation_result.get('stage') == self.SECURITY_STAGE_NAME else None,
                }

            # Below code is used to track if an iteration fail into the same erro. 
            # You can edit this "Track xx errors" section according to your needs.
            # error_key = f"{evaluation_result['stage']}:{str(evaluation_result['error'])}"
            # error_counts[error_key] = error_counts.get(error_key, 0) + 1
            
            # if error_counts[error_key] > self.max_same_error_attempts:
            #     print(f"Failed after {error_counts[error_key]} attempts with the same error")
            #     return {
            #         'success': False,
            #         'reason': 'max_same_error_attempts_exceeded',
            #         'error': evaluation_result
            #     }

            # Generate feedback
            feedback, feedback_level = self.generate_error_feedback(
                evaluation_result,
                stage_attempt_count,
                template_path
            )

            # Update feedback level
            if self.FEEDBACK_LEVELS.index(feedback_level) > self.FEEDBACK_LEVELS.index(highest_feedback_level):
                highest_feedback_level = feedback_level
            
            # Add the failed attempt and feedback to conversation history
            conversation_history.append({
                "role": "user",
                "content": f"The previous template had issues. Given feedback: {feedback}\nPlease generate an improved version of the template that addresses these issues."
            })
            
            iteration += 1
            current_stage = evaluation_result.get('stage')
            if current_stage in stages_error_count:
                stages_error_count[current_stage] += 1
            else:
                print(f"[WARNING] Unknown stage '{current_stage}' — skipping counter increment")

        
        return {
            'template_path': template_path,
            'success': False,
            'reason': 'max_iterations_exceeded',
            'failed_stage': evaluation_result['stage'],
            'iterations': iteration - 1,
            'highest_feedback_level': highest_feedback_level,
            'conversation_history': conversation_history
        }

    def _trim_history_for_limits(self, conversation_history, keep_last_n_messages=4, max_chars=500000):
        # 131,000 tokens is roughly 500,000 chars. We set a safe limit of ~350,000 chars for input.
        if len(conversation_history) <= 4:
            return conversation_history
            
        system_msg = [conversation_history[0]] # System Prompt
        user_prompt = [conversation_history[1]] # Original user prompt (business need)
        
        # Keep only the last N messages (e.g., the last 2 assistant responses and last 2 feedback prompts)
        recent_history = conversation_history[2:][-keep_last_n_messages:] if len(conversation_history) > 2 else []
        
        trimmed = system_msg + user_prompt + recent_history
        
        # Character-based emergency truncation for massive templates
        total_chars = sum(len(str(m.get("content", ""))) for m in trimmed)
        if total_chars > max_chars:
            for m in trimmed:
                # Truncate assistant generated templates if they are massive
                if m["role"] == "assistant" and len(m["content"]) > 10000:
                    m["content"] = m["content"][:10000] + "\n... [TEMPLATE TRUNCATED DUE TO LENGTH LIMITS] ...\n"
                    
        return trimmed

    def generate_plan_response(self, conversation_history):
        """Helper method to get the CoT plan without parsing for YAML tags or saving to file."""
        safe_history = self._trim_history_for_limits(conversation_history)
        
        if self.llm_type == "gemini":
            gemini_messages = [msg["content"] for msg in conversation_history if msg["role"] != "system"]
            response = self.model.generate_content(
                "\n".join(gemini_messages),
                generation_config=genai.GenerationConfig(max_output_tokens=8000, temperature=0.2)
            )
            return response.text
            
        elif self.llm_type == "gpt" and self.llm_model == "o3-mini":
            system_content = conversation_history[0]["content"]
            response = self.model.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "system", "content": system_content}] + conversation_history[1:],
                max_completion_tokens=8000,
            )
            return response.choices[0].message.content
            
        elif self.llm_type in ["gpt", "deepseek", "github", "ollama"]:
            model_name = self.llm_model.replace("openrouter/", "") if self.llm_type == "deepseek" else self.llm_model
            system_content = conversation_history[0]["content"]
            response = self.model.chat.completions.create(
                model=model_name,
                messages=[{"role": "system", "content": system_content}] + conversation_history[1:],
                max_tokens=8000,
                temperature=0.2
            )
            return response.choices[0].message.content

        elif self.llm_type == "claude":
            system_content = conversation_history[0]["content"]
            response = self.model.messages.create(
                model=self.llm_model,
                system=system_content,
                messages=conversation_history[1:],
                max_tokens=8000,
                temperature=0.2
            )
            return response.content[0].text


    def generate_template_with_history(self, conversation_history, iteration_num, row_num):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"{self.output_base_path}{self.llm_type}/{self.llm_model}/"
        safe_history = self._trim_history_for_limits(conversation_history)
        
        if self.llm_type == "gemini":
            # Convert conversation history to Gemini format
            gemini_messages = []
            for msg in conversation_history:
                if msg["role"] != "system":  # Gemini doesn't support system messages
                    gemini_messages.append(msg["content"])
        
            response = self.model.generate_content(
                "\n".join(gemini_messages),
                generation_config=genai.GenerationConfig(
                    max_output_tokens=8000,
                    temperature=0.1,
                )
            )
            content = response.text
        
        elif self.llm_type == "gpt" and self.llm_model == "o3-mini":
            # Get system content from first message and remove it from messages
            system_content = conversation_history[0]["content"]
            messages = conversation_history[1:]  # All messages after system

            response = self.model.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "system", "content": system_content}] + messages,
                max_completion_tokens=8000,
            )
            content = response.choices[0].message.content
        
        elif self.llm_type == "gpt":
            # Get system content from first message and remove it from messages
            system_content = conversation_history[0]["content"]
            messages = conversation_history[1:]  # All messages after system

            response = self.model.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "system", "content": system_content}] + messages,
                max_tokens=8000,
                temperature=0
            )
            content = response.choices[0].message.content

        elif self.llm_type == "deepseek":
            model_name = self.llm_model.replace("openrouter/", "")
            system_content = safe_history[0]["content"]
            messages = safe_history[1:]

            response = self.model.chat.completions.create(
                model=model_name,
                messages=[{"role": "system", "content": system_content}] + messages,
                max_tokens=8000,
                temperature=0
            )
            content = response.choices[0].message.content

            if content is None or content.strip() == "":
                print(f"Warning: Received empty response from Deepseek model {model_name}. Check API usage and model status.")
                content = "<template_planning>\n<iac_template>\nAWSTemplateFormatVersion: '2010-09-09'\nDescription: Empty template generated due to model response issue.\nResources:\n  EmptyResource:\n    Type: 'AWS::CloudFormation::WaitConditionHandle'\n</iac_template>\n</template_planning>"
        
        elif self.llm_type == "github":
            model_name = self.llm_model
            system_content = safe_history[0]["content"]
            messages = safe_history[1:]

            response = self.model.chat.completions.create(
                model=model_name,
                messages=[{"role": "system", "content": system_content}] + messages,
                max_tokens=8000,
                temperature=0
            )
            content = response.choices[0].message.content

            if content is None or content.strip() == "":
                print(f"Warning: Received empty response from Deepseek model {model_name}. Check API usage and model status.")
                content = "<template_planning>\n<iac_template>\nAWSTemplateFormatVersion: '2010-09-09'\nDescription: Empty template generated due to model response issue.\nResources:\n  EmptyResource:\n    Type: 'AWS::CloudFormation::WaitConditionHandle'\n</iac_template>\n</template_planning>"

        elif self.llm_type == "claude":  # claude
            # Get system content from first message and remove it from messages
            system_content = conversation_history[0]["content"]
            messages = conversation_history[1:]  # All messages after system

            response = self.model.messages.create(
                model=self.llm_model,
                system=system_content,
                messages=messages,
                max_tokens=8000,
                temperature=0
            )
            content = response.content[0].text
        elif self.llm_type == "ollama":
            system_content = safe_history[0]["content"]
            messages = safe_history[1:]
            response = self.model.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "system", "content": system_content}] + messages,
                max_tokens=8000,
                temperature=0
            )
            content = response.choices[0].message.content

        
        # Process and save the template
        # Remove content within <template_planning>...</template_planning>
        start_tag = "<template_planning>"
        end_tag = "</template_planning>"
        start_pos = content.find(start_tag)
        end_pos = content.find(end_tag, start_pos)
        if start_pos != -1 and end_pos != -1:
            content = content[:start_pos] + content[end_pos + len(end_tag):]
            
        # Extract content within <iac_template> tags
        iac_start_tag = "<iac_template>"
        iac_end_tag = "</iac_template>"
        iac_start_pos = content.find(iac_start_tag)
        iac_end_pos = content.find(iac_end_tag, iac_start_pos)
        
        if iac_start_pos != -1 and iac_end_pos != -1:
            # Extract content between tags and strip whitespace
            content = content[iac_start_pos + len(iac_start_tag):iac_end_pos].strip()
        else:
            print(f"Warning: <iac_template> tags not found in template content")
            # Fallback to looking for AWSTemplateFormatVersion
            aws_version_pos = content.find("AWSTemplateFormatVersion")
            if aws_version_pos != -1:
                content = content[aws_version_pos:].strip()
                # Look for triple backticks after the template, which deepseek-chat like to put his natural langauge update after.
                backticks_pos = content.find("```")
                if backticks_pos != -1:
                    content = content[:backticks_pos].strip()
            else:
                print(f"Warning: AWSTemplateFormatVersion not found in template content")
        
        os.makedirs(output_path, exist_ok=True)
        output_file = f"{output_path}row_{row_num}_update_{iteration_num}_template_{timestamp}.yaml"
        
        with open(output_file, 'w') as f:
            f.write(content)
        
        return output_file

    def generate_conversation_history(self, conversation_history, output_base_path, is_success, row_number):
        """
        Save the conversation history in a structured format.
        
        Args:
            conversation_history: List of conversation messages
            output_base_path: Base path for output directory
            is_success: Whether the generation was successful
            row_number: Row number from the CSV for unique identification
        """
        # Create output directory with LLM type
        output_path = os.path.join(output_base_path, self.llm_type, self.llm_model)
        os.makedirs(output_path, exist_ok=True)
        
        # Generate a filename based on timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        row_identifier = f"row{row_number}_" if row_number is not None else ""
        filename = f"{output_path}/conversation_{row_identifier}{is_success}_{timestamp}.txt"
        
        # Format and save the conversation history
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"Conversation History - {self.llm_type} - Row: {row_number} - Success: {is_success} - {timestamp}\n")
            f.write("=" * 80 + "\n\n")
            
            for i, message in enumerate(conversation_history, 1):
                # Write message header
                f.write(f"Message {i}\n")
                f.write(f"Role: {message['role']}\n")
                f.write("-" * 40 + "\n")
                
                # Write message content
                if message['role'] == "assistant":
                    # For assistant messages, try to identify if it's a template
                    if message['content'].strip().startswith("AWSTemplateFormatVersion"):
                        f.write("[Generated Template Content]\n")
                        f.write(message['content'][:self.TEMPLATE_SHOWN_CHARACTERS] + "...\n")  # Show first xx chars of template
                    else:
                        f.write(message['content'] + "\n")
                else:
                    f.write(message['content'] + "\n")
                
                f.write("\n" + "=" * 80 + "\n\n")
        
        return filename

    @classmethod
    def generate_error_history_csv(cls, output_path):
        """
        Convert the error history to a CSV file, appending to existing file if it exists.
        
        Args:
            output_path: Path to save the error history CSV
        """
        if not cls.error_history:
            print("No errors to record")
            return None
            
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Convert current error history to DataFrame
        new_df = pd.DataFrame(cls.error_history)
        
        # If file exists, append to it
        if os.path.exists(output_path):
            existing_df = pd.read_csv(output_path)
            # Combine existing and new data
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            combined_df.to_csv(output_path, index=False)
        else:
            new_df.to_csv(output_path, index=False)
        
        # Clear the error history after saving
        cls.error_history = []
        
        return output_path


def process_ioc_csv(input_csv, output_csv, llm_type, llm_model, start_row=0, end_row=None, prompt_strategy="cgo"):
    generator = IterativeTemplateGenerator(llm_type, llm_model, prompt_strategy=prompt_strategy)
    df = pd.read_csv(input_csv, encoding='latin-1')
    df['ground_truth_path'] = df['ground_truth_path'].str.replace('\\', '/', regex=False)
    df['ground_truth_path'] = df['ground_truth_path'].str.replace('Data/', '../Data/', regex=False)

    if os.path.exists(output_csv):
        try:
            existing_results_df = pd.read_csv(output_csv)
            if not existing_results_df.empty and 'row_number' in existing_results_df.columns:
                last_processed_row = existing_results_df['row_number'].max()
                if pd.notna(last_processed_row):
                    # Resume from the row immediately after the last successfully processed one
                    start_row = max(start_row, int(last_processed_row) + 1)
                    print(f"\n[INFO] Found existing output file. Resuming execution from row {start_row}.\n")
        except Exception as e:
            print(f"[WARNING] Could not read existing output file to resume: {e}")

    # Validate and adjust row ranges
    end_row = len(df) if end_row is None else min(end_row, len(df))
    if start_row >= end_row:
        print(f"All rows up to {end_row} have already been processed. Exiting.")
        return
    
    print(f"Processing {end_row - start_row} rows from {start_row} to {end_row-1} row")

    # Ensure output directories exist
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    error_csv_path = f"Result/error_tracking/{llm_model}_error_history-{prompt_strategy}.csv"
    os.makedirs(os.path.dirname(error_csv_path), exist_ok=True)
    
    try:
        for index, row in df.iloc[start_row:end_row].iterrows():
            try:
                result = generator.process_template(row['prompt'], row['ground_truth_path'], index)
                row_result = {
                    # Basic Information
                    'row_number': index,
                    'prompt': row['prompt'],
                    'ground_truth_path': row['ground_truth_path'],
                    'final_template_path': result.get('template_path'),

                    # Success Metrics
                    'success': result['success'],
                    'failure_reason': result.get('reason', None),
                    'error_message': result.get('error', None),
                    'failed_at_stage': result.get('failed_stage', None) if not result['success'] else None,
                    'total_iterations': result.get('iterations'),    
                    'highest_feedback_level': result.get('highest_feedback_level'),

                    # Coverage and Accuracy Metrics
                    'coverage_percentage': result.get('coverage_percentage', None),
                    'accuracy_percentage': result.get('accuracy_percentage', None),
                    'security_pass_percentage': result.get('security_pass_percentage', None),
                    # 'missing_resources': result.get('missing_resources', []),
                    # 'extra_resources': result.get('extra_resources', []),

                    # Model Information
                    # 'llm_type': generator.llm_type,
                    # 'llm_model': generator.llm_model,
                }
                generator.generate_conversation_history(result['conversation_history'], "llm_generated_data/iterative/history", result['success'], index)

                # 2. CONTINUOUS RESULT SAVING: Append to the CSV immediately
                results_df = pd.DataFrame([row_result])
                if os.path.exists(output_csv):
                    results_df.to_csv(output_csv, mode='a', header=False, index=False)
                else:
                    results_df.to_csv(output_csv, mode='w', header=True, index=False)
                
                # 3. CONTINUOUS ERROR TRACKING: Flush error history to CSV immediately
                IterativeTemplateGenerator.generate_error_history_csv(error_csv_path)
                
                print(f"[SUCCESS] Saved data for row {index} to disk.")
            except Exception as e:
                print(f"[ERROR] Failed at row {index}. Reason: {e}.")
                # Flush any captured errors to disk even if the row hit an unhandled exception
                IterativeTemplateGenerator.generate_error_history_csv(error_csv_path)
    except KeyboardInterrupt:
        print("\n[INFO] Execution interrupted by user (Ctrl+C). All progress up to the last completed row has been safely saved.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[FATAL ERROR] Pipeline crashed: {e}")


# Start
if __name__ == "__main__":
    print("IaCGen Starting")
    prompt_strategy = "cgo"  # "two_step", "scot", or "cgo"
    input_csv = "../Data/iac_basic.csv"
    llm_type = "deepseek"  # "gemini", "gpt", "claude", or "deepseek"
    # llm_model = "gpt-5-mini"  # [gemini-1.5-flash, gpt-4o, o3-mini, o1, claude-3-5-sonnet-20241022, claude-3-7-sonnet-20250219, deepseek-chat [V3], deepseek-reasoner [R1]]
    llm_model = "openrouter/arcee-ai/trinity-large-preview:free"  # [gemini-1.5-flash, gpt-4o, o3-mini, o1, claude-3-5-sonnet-20241022, claude-3-7-sonnet-20250219, deepseek-chat [V3], deepseek-reasoner [R1]]
    output_csv = f"Result/iterative_{llm_model}_results-{prompt_strategy}.csv"
    start_row = 0
    end_row = 153

    print(f"Starting iterative generation with {llm_type} model")

    process_ioc_csv(input_csv, output_csv, llm_type, llm_model, start_row=start_row, end_row=end_row, prompt_strategy=prompt_strategy)  # start row include, end row exclude

    print(f"Generation completed. Results saved to: {output_csv}")
