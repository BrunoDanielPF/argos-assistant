# Dataset Curation

Use this skill when reviewing or cleaning Argos datasets.

Workflow:
- Validate JSONL structure before judging quality.
- Check labels, capabilities, arguments, and expected outputs.
- Remove duplicates and near-duplicates.
- Balance common intents against edge cases.
- Flag unsafe rows, leaked secrets, ambiguous commands, and impossible expected actions.

Output:
- Summary of row counts.
- Rejected rows with reasons.
- Suggested fixes.
- Remaining risks in the dataset.
