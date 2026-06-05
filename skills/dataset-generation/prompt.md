# Dataset Generation

Use this skill when generating datasets for Argos model tuning or evaluation.

Workflow:
- Define the target behavior and output schema before writing examples.
- Separate training examples from evaluation examples.
- Include realistic Portuguese and English user commands when relevant.
- Include negative examples for unsupported or unsafe requests.
- Avoid adding secrets, personal data, or machine-specific paths unless synthetic.

Output:
- Dataset purpose.
- JSONL schema.
- Example rows.
- Validation checks for duplicates, malformed JSON, and unsafe content.
