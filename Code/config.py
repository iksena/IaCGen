"""Central configuration for IaCGen.

All tuneable constants live here. Import from this module everywhere else
to avoid magic numbers and repeated os.getenv() calls scattered across files.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# API Keys (loaded from .env)
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMIN_API_KEY", "")
CHATGPT_API_KEY = os.getenv("CHATGPT_API_KEY", "")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# ---------------------------------------------------------------------------
# Feedback and iteration limits
# ---------------------------------------------------------------------------
SIMPLE_LEVEL_MAX_ITERATIONS = 2
MODERATE_LEVEL_MAX_ITERATIONS = 4
ADVANCED_LEVEL_MAX_ITERATIONS = 4
MAX_ITERATIONS = 30

# ---------------------------------------------------------------------------
# Feedback levels (ordered: simple -> moderate -> advanced)
# ---------------------------------------------------------------------------
FEEDBACK_LEVELS = ["simple", "moderate", "advanced"]

# ---------------------------------------------------------------------------
# Validation stage identifiers
# ---------------------------------------------------------------------------
YAML_STAGE = "yaml_validation"
SYNTAX_STAGE = "syntax_validation"
DEPLOYMENT_STAGE = "deployment"

# ---------------------------------------------------------------------------
# File system paths
# ---------------------------------------------------------------------------
OUTPUT_BASE_PATH = "llm_generated_data/template/iterative/"
CONVERSATION_HISTORY_PATH = "llm_generated_data/iterative/history"
ERROR_TRACKING_DIR = "result/error_tracking"

# ---------------------------------------------------------------------------
# Display settings
# ---------------------------------------------------------------------------
# Maximum characters of a template to print in advanced feedback / history logs
TEMPLATE_SHOWN_CHARACTERS = 1000

# ---------------------------------------------------------------------------
# LLM generation defaults
# ---------------------------------------------------------------------------
DEFAULT_MAX_TOKENS = 8000
DEFAULT_TEMPERATURE = 0
