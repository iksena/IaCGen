"""IaCGen entry point.

Edit the configuration block below to choose your LLM and row range,
then run from the repository root::

    python Code/main.py

Supported llm_type values : gemini | gpt | claude | deepseek
Example model identifiers  : gemini-1.5-flash | gpt-4o | o3-mini | o1
                             claude-3-5-sonnet-20241022 | claude-3-7-sonnet-20250219
                             deepseek-chat (V3) | deepseek-reasoner (R1)
"""
from dataset.loader import process_ioc_csv

# ---------------------------------------------------------------------------
# Configuration — edit here
# ---------------------------------------------------------------------------
INPUT_CSV = "../Data/iac_basic.csv"
LLM_TYPE  = "deepseek"                        # gemini | gpt | claude | deepseek
LLM_MODEL = "openrouter/deepseek/deepseek-r1-0528:free"
START_ROW = 0
END_ROW   = 153                             # set to None to process all rows
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    output_csv = f"Result/iterative_{LLM_MODEL}_results.csv"
    print(f"IaCGen starting — model: {LLM_TYPE}/{LLM_MODEL}")
    process_ioc_csv(INPUT_CSV, output_csv, LLM_TYPE, LLM_MODEL, start_row=START_ROW, end_row=END_ROW)
    print(f"Generation completed. Results saved to: {output_csv}")
