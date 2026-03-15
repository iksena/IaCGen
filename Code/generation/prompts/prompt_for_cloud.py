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
TWO_STEP_PLAN_BOTTOM = f"""
</business_need>

Instructions for your plan:
1. List the key AWS services required.
2. Identify all necessary properties and dependencies (e.g., Internet Gateways attached to VPCs before provisioning Elastic IPs).
3. If specific properties (like CIDR blocks or Instance Types) are missing, explicitly state the safe AWS defaults you will use.
4. Plan out how to dynamically fetch resources like AMIs using SSM Parameter Store to avoid hardcoding.

{AWS_BEST_PRACTICES_REMINDER}

Do NOT write any CloudFormation YAML yet. Only provide your detailed reasoning and architecture plan."""

# Step 2: The Generation Prompt
TWO_STEP_GENERATE_PROMPT = """Excellent. Based on the architecture plan you just created and the original business need, please generate the complete CloudFormation YAML template.

CRITICAL INSTRUCTIONS:
1. Start the template with 'AWSTemplateFormatVersion'.
2. Provide all required properties for each resource and ensure proper YAML syntax.
3. Write your complete CloudFormation YAML template strictly inside <iac_template></iac_template> tags.
4. Do NOT include any markdown code blocks (like ```yaml) inside or outside the tags."""

# ─────────────────────────────────────────────
# SCOT: Structured Chain-of-Thought Prompting
# ─────────────────────────────────────────────

SCOT_SYSTEM_PROMPT = """You are an Expert AWS Cloud Architect and DevOps Engineer.
Your job is to design robust, production-ready AWS environments and then implement them using AWS CloudFormation.
You operate in a strict automated pipeline."""

# Phase 1 – Generate the SCoT plan (few-shot, 3 examples from ground truth below)
SCOT_PLAN_TOP = """Analyze the following business need and produce a structured deployment plan using ONLY sequence, branch, and loop constructs.
Format each plan as:
  Input: <parameters the template will accept>
  Output: <AWS resource types that will be created>
  1. sequence step
  2. if <condition>
  3.   branch step
  4. for each <item>
  5.   loop step

Here are three examples spanning easy to complex deployments:

--- Example 1 (Difficulty Level 1 – Single Resource) ---
Business need: We need a CloudFormation template that creates an AWS SQS queue with basic configuration.
Input: (none)
Output: AWS::SQS::Queue
1. Define AWS::SQS::Queue resource MyQueue
2. Set VisibilityTimeout to 5

--- Example 2 (Difficulty Level 3 – Multi-Resource with Cross-References) ---
Business need: We need a CloudFormation template that creates an Amazon S3 bucket for website hosting and with a DeletionPolicy.
Input: (none)
Output: AWS::S3::Bucket, AWS::S3::BucketPolicy
1. Define AWS::S3::Bucket resource S3Bucket
2.   Set WebsiteConfiguration IndexDocument index.html ErrorDocument error.html
3.   Set DeletionPolicy Retain and UpdateReplacePolicy Retain
4.   if bucket must be publicly readable for website hosting
5.     Set PublicAccessBlockConfiguration all four flags to false
6. Define AWS::S3::BucketPolicy resource BucketPolicy
7.   Set PolicyDocument Version 2012-10-17 Statement Allow s3:GetObject Principal *
8.   Reference bucket ARN using !Join on arn:aws:s3::: + !Ref S3Bucket + /*
9.   Set Bucket property to !Ref S3Bucket
10. Define Outputs
11.   WebsiteURL via !GetAtt S3Bucket.WebsiteURL
12.   S3BucketSecureURL via !Join https:// + !GetAtt S3Bucket.DomainName

--- Example 3 (Difficulty Level 5 – Full Production Pipeline) ---
Business need: We need a CloudFormation template that creates an automated deployment pipeline for the Etherpad application using AWS CodeDeploy. The template should deploy Etherpad on EC2 instances within an Auto Scaling group across two subnets, fronted by an internet-facing Application Load Balancer for traffic distribution. It must provision a MySQL RDS instance for database storage and integrate AWS Systems Manager (SSM) for secure parameter storage. The solution should automate instance provisioning with a launch template that installs dependencies (Node.js, CodeDeploy agent) and signals CloudFormation upon readiness. An S3 bucket stores deployment artifacts, while CodeDeploy resources manage application updates.
Input:
  - DBPassword (String, NoEcho, Default: admin1234, secure DB password)
  - InstanceType (String, Default: t3.micro, AllowedValues: [t3.micro, t3.small, t3.medium])
  - KeyName (String, Default: default-key, SSH key pair)
Output:
  AWS::EC2::VPC, AWS::EC2::Subnet (x2), AWS::EC2::InternetGateway,
  AWS::EC2::RouteTable, AWS::ElasticLoadBalancingV2::LoadBalancer,
  AWS::ElasticLoadBalancingV2::TargetGroup, AWS::ElasticLoadBalancingV2::Listener,
  AWS::AutoScaling::AutoScalingGroup, AWS::AutoScaling::LaunchTemplate,
  AWS::RDS::DBInstance, AWS::RDS::DBSubnetGroup,
  AWS::S3::Bucket, AWS::SSM::Parameter,
  AWS::CodeDeploy::Application, AWS::CodeDeploy::DeploymentGroup,
  AWS::IAM::Role (x2 — EC2 instance role, CodeDeploy service role), AWS::IAM::InstanceProfile
1. Define Parameters DBPassword NoEcho, InstanceType with AllowedValues, KeyName
2. Define VPC with CIDR 10.0.0.0/16
3. Define InternetGateway and attach to VPC via VPCGatewayAttachment
4. for each of two AZs (us-east-1a, us-east-1b)
5.   Define AWS::EC2::Subnet with public CIDR (10.0.1.0/24, 10.0.2.0/24) MapPublicIpOnLaunch true
6. Define RouteTable with route 0.0.0.0/0 → InternetGateway
7. for each Subnet
8.   Associate subnet with RouteTable via SubnetRouteTableAssociation
9. Define AWS::EC2::SecurityGroup ALBSecurityGroup allowing HTTP port 80 ingress 0.0.0.0/0
10. Define AWS::EC2::SecurityGroup EC2SecurityGroup allowing HTTP port 80 ingress from ALBSecurityGroup only
11. Define AWS::EC2::SecurityGroup RDSSecurityGroup allowing MySQL port 3306 ingress from EC2SecurityGroup only
12. Define AWS::ElasticLoadBalancingV2::LoadBalancer internet-facing across both subnets
13. Define AWS::ElasticLoadBalancingV2::TargetGroup port 80 HTTP targeting EC2 ASG
14. Define AWS::ElasticLoadBalancingV2::Listener port 80 forwarding to TargetGroup
15. Define AWS::IAM::Role EC2InstanceRole trusting ec2.amazonaws.com with SSM + CodeDeploy + S3 permissions
16. Define AWS::IAM::InstanceProfile wrapping EC2InstanceRole
17. Define AWS::IAM::Role CodeDeployServiceRole trusting codedeploy.amazonaws.com with AWSCodeDeployRole policy
18. Define AWS::S3::Bucket ArtifactsBucket for deployment artifacts
19. Define AWS::SSM::Parameter storing DB connection string referencing RDS endpoint
20. Define AWS::RDS::DBSubnetGroup across both subnets
21. Define AWS::RDS::DBInstance MySQL db.t3.micro
22.   Set MasterUsername admin MasterUserPassword !Ref DBPassword
23.   Set DBSubnetGroupName !Ref DBSubnetGroup VPCSecurityGroups [RDSSecurityGroup]
24.   if production environment
25.     Set MultiAZ true
26.   else
27.     Set MultiAZ false
28. Define AWS::AutoScaling::LaunchTemplate
29.   Set ImageId via SSM resolve latest Amazon Linux 2 AMI
30.   Set InstanceType !Ref InstanceType KeyName !Ref KeyName
31.   Set IamInstanceProfile !Ref EC2InstanceProfile
32.   Set UserData script to install Node.js, CodeDeploy agent, signal cfn-signal on success
33. Define AWS::AutoScaling::AutoScalingGroup MinSize 1 MaxSize 3 DesiredCapacity 2
34.   Set VPCZoneIdentifier [Subnet1, Subnet2]
35.   Set TargetGroupARNs [TargetGroup]
36.   Add CreationPolicy ResourceSignal Count 2 Timeout PT10M
37. Define AWS::CodeDeploy::Application EtherpadApp ComputePlatform Server
38. Define AWS::CodeDeploy::DeploymentGroup
39.   Set ApplicationName !Ref EtherpadApp
40.   Set ServiceRoleArn !GetAtt CodeDeployServiceRole.Arn
41.   Set AutoScalingGroups [AutoScalingGroup]
42.   Set LoadBalancerInfo TargetGroupInfoList [TargetGroup]
---

Now produce the SCoT plan for the following business need:

<business_need>
"""


SCOT_PLAN_BOTTOM = f"""
</business_need>

{AWS_BEST_PRACTICES_REMINDER}

Output ONLY the structured plan in the Input/Output/numbered format above. Do NOT write any CloudFormation YAML yet."""

# Phase 2 – same generation prompt as TWO_STEP
SCOT_GENERATE_PROMPT = TWO_STEP_GENERATE_PROMPT


# ─────────────────────────────────────────────
# CGO: Chain of Grounded Objectives
# ─────────────────────────────────────────────

CGO_SYSTEM_PROMPT = """You are an Expert AWS Cloud Architect and DevOps Engineer.
Your job is to design robust, production-ready AWS environments and then implement them using AWS CloudFormation.
You operate in a strict automated pipeline."""

# Phase 1 – Ask the LLM to generate concise functional objectives (no fixed structure)
CGO_PLAN_TOP = """Analyze the following business need and generate a compact, numbered list of functional objectives
that a CloudFormation template must satisfy. Each objective must be a concrete, verifiable deployment requirement.

Here is one example at medium difficulty:

--- Example (Difficulty Level 3) ---
Business need: We need a CloudFormation template that creates an Amazon S3 bucket for website hosting and with a DeletionPolicy.
Objectives:
1. Provision an AWS::S3::Bucket with WebsiteConfiguration (IndexDocument: index.html, ErrorDocument: error.html)
2. Disable all four PublicAccessBlock flags to allow public website reads
3. Apply DeletionPolicy: Retain and UpdateReplacePolicy: Retain to protect bucket data on stack deletion
4. Provision an AWS::S3::BucketPolicy granting s3:GetObject to Principal * scoped to all objects in the bucket
5. Output the WebsiteURL (via WebsiteURL attribute) and the HTTPS DomainName of the bucket
---

Now generate the objectives list for the following business need:

<business_need>
"""


CGO_PLAN_BOTTOM = f"""
</business_need>

{AWS_BEST_PRACTICES_REMINDER}

Output ONLY the numbered objectives list (5–10 items). Do NOT write any CloudFormation YAML yet."""

# Phase 2 – same generation prompt
CGO_GENERATE_PROMPT = TWO_STEP_GENERATE_PROMPT 

# ─────────────────────────────────────────────
# CDK: CDK Assertion-Guided Generation (Python)
# ─────────────────────────────────────────────

CDK_SYSTEM_PROMPT = """You are an Expert AWS Cloud Architect and DevOps Engineer.
Your job is to design robust, production-ready AWS environments and implement them using AWS CloudFormation.
You operate in a strict automated pipeline."""

# Phase 1 – Generate Python CDK assertions from business need
CDK_ASSERTION_TOP = """You are an expert AWS CDK engineer. Given the following business need,
generate Python CDK v2 assertion code using the aws_cdk.assertions library.

You will generate ONLY the body of a pytest test function. The imports, Template loading,
and pytest fixture are already handled by a boilerplate wrapper — do NOT include them.

The test function signature you must implement is:
    def test_template(template: Template):

The `template` parameter is a fully loaded aws_cdk.assertions.Template object.
You have access to these already-imported names — use them directly, do not re-import:
    Template, Match, Capture   (from aws_cdk.assertions)
    pytest                     (standard pytest)

Available assertion methods:
- template.has_resource_properties(type, props)
- template.has_resource(type, props)
- template.resource_count_is(type, count)
- template.has_output(id, props)
- template.has_mapping(id, props)
- template.has_condition(id, props)
- template.has_parameter(id, props)
- template.find_resources(type, props)
- template.find_outputs(id, props)

Available Match helpers:
    Match.object_like, Match.object_equals, Match.array_with, Match.array_equals,
    Match.string_like_regexp, Match.any_value, Match.absent, Match.not_

Use Capture() when a value must be inspected but is dynamically generated.

Rules:
- Start directly with 'def test_template(template: Template):'
- Assert every resource type, key property values, outputs, and parameters the business need implies.
- Use Match.string_like_regexp for dynamic values (AMI IDs, ARNs, account IDs).
- Use Match.absent() to assert properties that must NOT exist.
- Do NOT include import statements.
- Do NOT include a fixture or any loading logic.
- Do NOT include any code outside the test function.

Business need:

<business_need>
"""

CDK_ASSERTION_BOTTOM = """
</business_need>

Output ONLY the test function inside <cdk_assertions> tags. No explanations, no imports."""

# Phase 2 – Generate CloudFormation template from business need + CDK assertions
CDK_GENERATE_TOP = """Based on the following business need and the CDK assertion test file below,
generate a complete, production-ready AWS CloudFormation YAML template that satisfies
the business need AND passes all provided CDK assertions.

<business_need>
"""

CDK_GENERATE_MIDDLE = """
</business_need>

The template MUST pass every assertion in the following CDK Python test file:

<cdk_assertions>
"""

CDK_GENERATE_BOTTOM = f"""
</cdk_assertions>

{AWS_BEST_PRACTICES_REMINDER}

CRITICAL INSTRUCTIONS:
1. Start the template with 'AWSTemplateFormatVersion'.
2. Provide all required properties for each resource.
3. Ensure proper YAML syntax and indentation.
4. Write your complete CloudFormation YAML template strictly inside <iac_template></iac_template> tags.
5. Do NOT include any markdown code blocks (like ```yaml) inside or outside the tags."""