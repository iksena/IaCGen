AWS_BEST_PRACTICES_REMINDER = """
### CRITICAL AWS BEST PRACTICES & LINTING RULES
To ensure the template deploys successfully and passes cfn-lint, you MUST adhere to the following rules based on common historical failures:

1. **Parameters & Missing Values:** - NEVER define Parameters without providing a safe `Default` value (e.g., default CIDR blocks, default dummy email addresses, or default KeyPair names like 'default-key'). The automated deployment will fail if parameters require manual input.
   - If a Parameter has an `AllowedPattern`, its `Default` value must strictly match that pattern.

2. **Hardcoding (AMIs & AZs):**
   - NEVER hardcode AMI IDs (e.g., ami-0c55...). Use AWS Systems Manager (SSM) Parameter Store to fetch the latest AMIs dynamically (e.g., 'resolve:ssm:/aws/service/ami-amazon-linux-latest/amzn2-ami-hvm-x86_64-gp2').
   - NEVER hardcode Availability Zones (e.g., 'us-east-1a'). Always use the `Fn::Select` and `Fn::GetAZs` intrinsic functions.

3. **S3 Bucket Modernization:**
   - Do NOT use the legacy `AccessControl` property for S3 Buckets. Use `AWS::S3::BucketPolicy` instead. 
   - If `AccessControl` is strictly required for some reason, you MUST also configure `OwnershipControls`.

4. **Resource Protection & Linting:**
   - If you specify a `DeletionPolicy` on a stateful resource (like a database or bucket), you MUST also include an `UpdateReplacePolicy`.
   - Do not use `Fn::Sub` (or `!Sub`) if the string does not contain any variables (e.g., `${Var}`).
   - Do not hallucinate properties. For example, do not add `FilterCriteria` or `Default` to properties where the CloudFormation schema does not allow them.

5. **Security & Runtimes:**
   - Use dynamic references (e.g., `{{resolve:secretsmanager:...}}` or `{{resolve:ssm-secure:...}}`) instead of raw Parameters for passing secrets or passwords.
   - For AWS Lambda, NEVER use deprecated runtimes (like `python3.8`). Always use the latest supported runtimes (e.g., `python3.12` or `nodejs20.x`).
   - Ensure AWS managed IAM Policy ARNs and Resource Type names are exact and currently valid (e.g., use `AWS::Logs::QueryDefinition`, not `AWS::CloudWatchLogs::QueryDefinition`).
"""

# Prompts used in IaCGen
# User Input Chain-of-thought Prompt where the iac problem will be placed in between the TOP and BOTTOM PROMPT when generation. 
TOP_PROMPT = "You are an expert AWS DevOps engineer with extensive experience in creating CloudFormation templates. Your task is to generate a valid, production ready and deployable AWS CloudFormation YAML template based on the following business need:\n\n<business_need>\n"
BOTTOM_PROMPT = f"""
</business_need>

Instructions:
1. Analyze the business need carefully.
2. Generate a complete CloudFormation YAML template that fulfills this need.
3. Be sure to fully specified all resources needed in the Resources section.
4. Ensure high accuracy and deployment success by following these guidelines:
    a. Start the template with 'AWSTemplateFormatVersion'.
    b. Include all necessary resources to meet the business need.
    c. Provide all required properties for each resource.
    d. Use proper YAML syntax and indentation.
    e. Follow AWS CloudFormation best practices and cloudformation-linter rules.
    f. End the template with the last property of the last resource.

{AWS_BEST_PRACTICES_REMINDER}

### OUTPUT FORMAT REQUIREMENTS
Before generating the final template, wrap your planning process in <template_planning> tags. In this section:
1. List the key AWS services mentioned or implied in the business need.
2. Outline the main sections of the CloudFormation template (e.g., Parameters, Mappings, Resources, Outputs).
3. Consider potential dependencies between resources and how to order them.
4. Think about any parameters or mappings that might be needed for flexibility.
5. Consider any outputs that would be useful for the user after stack creation.

This planning process will help reduce errors and improve deployment success rate. It's okay for this section to be quite long.

After your planning process, provide the complete CloudFormation YAML template inside <iac_template> tags.
Do NOT include any explanations, markdown formatting (like ```yaml), or backticks inside or outside of these tags.
"""

# System Prompt
FORMATE_SYSTEM_PROMPT = """You are an Expert AWS CloudFormation Architect. Your task is to generate and improve templates based on feedback. 
You operate within an automated evaluation pipeline with a strict limit of 5 attempts to succeed. Therefore, your template MUST pass YAML validation, syntax linting (cfn-lint), and AWS deployment on the very first try.
Please write your complete CloudFormation YAML template strictly inside <iac_template></iac_template> tags without any markdown wrappers.
"""


# Terraform prompt used in IaC-Eval
FORMATE_SYSTEM_PROMPT_TF = "You are TerraformAI, an AI agent that builds and deploys Cloud Infrastructure written in Terraform HCL. Generate a description of the Terraform program you will define, followed by a single Terraform HCL program in response to each of my Instructions. Make sure the configuration is deployable. Create IAM roles as needed. If variables are used, make sure default values are supplied. Be sure to include a valid provider configuration within a valid region. Make sure there are no undeclared resources (e.g., as references) or variables, i.e., all resources and variables needed in the configuration should be fully specified. Please write your complete HCL template inside <iac_template></iac_template> tags."
TOP_PROMPT_TF = "Here is the actual business need description which you should follow to build and deploy Cloud Infrastructure written in Terraform HCL: "


# System prompt for more consistent YAML template output (Not used in IaCGen)
TEMPLATE_GENERATE_PROMPT = """You are an expert CloudFormation engineer. Generate only valid CloudFormation YAML. Do not include any explanations, markdown formatting, or backticks. The template should start with AWSTemplateFormatVersion and end with the last property. You should include all the necessary resources for the given need. Below is the description for the required template:"""
SYSMTE_TEMPLATE_GENERATE_PROMPT = """You are an expert CloudFormation engineer. Generate only valid CloudFormation YAML. Do not include any explanations, markdown formatting, or backticks. The template should start with AWSTemplateFormatVersion and end with the last property. You should include all the necessary resources for the given need."""
GPT_TEMPLATE_GENERATE_HELPER_PROMPT = "Can you help us write the CloudFormation template?"
SYSTEM_PROMPT = "You are an expert in AWS CloudFormation template generation. Your task is to generate and improve templates based on feedback."

# --- TWO-STEP CoT PROMPTS ---
TWO_STEP_SYSTEM_PROMPT = """You are an Expert AWS Cloud Architect and DevOps Engineer. 
Your job is to design robust, production-ready AWS environments and then implement them using AWS CloudFormation.
You operate in a strict automated pipeline."""

# Step 1: The Planning Prompt
TWO_STEP_PLAN_TOP = "Please analyze the following business need and create a detailed architectural deployment plan:\n\n<business_need>\n"
TWO_STEP_PLAN_BOTTOM = """
</business_need>

Instructions for your plan:
1. List the key AWS services required.
2. Identify all necessary properties and dependencies (e.g., Internet Gateways attached to VPCs before provisioning Elastic IPs).
3. If specific properties (like CIDR blocks or Instance Types) are missing, explicitly state the safe AWS defaults you will use.
4. Plan out how to dynamically fetch resources like AMIs using SSM Parameter Store to avoid hardcoding.

Do NOT write any CloudFormation YAML yet. Only provide your detailed reasoning and architecture plan."""

# Step 2: The Generation Prompt
TWO_STEP_GENERATE_PROMPT = """Excellent. Based on the architecture plan you just created and the original business need, please generate the complete CloudFormation YAML template.

CRITICAL INSTRUCTIONS:
1. Start the template with 'AWSTemplateFormatVersion'.
2. Provide all required properties for each resource and ensure proper YAML syntax.
3. Write your complete CloudFormation YAML template strictly inside <iac_template></iac_template> tags.
4. Do NOT include any markdown code blocks (like ```yaml) inside or outside the tags."""