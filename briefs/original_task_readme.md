# Quality Control Pipeline - Mini Agent

## Task Overview

Build an automated quality control pipeline that processes manufacturing inspection reports and alerts stakeholders when defect thresholds are exceeded.

## The Challenge

You have access to a collection of inspection reports stored as JSON files in the `data/inspection_reports/` directory. Each report contains production statistics and quality assurance findings from various manufacturing facilities.

Your task is to build a system that processes these reports and notifies stakholders when quality issues exceed acceptable levels.

## Defect Threshold Rules

An email alert should be sent to the stakeholder if **any** of the following conditions are met:

- Major defects exceed **1%** of total production
- Minor defects exceed **3%** of total production  
- Overall defects (major + minor) exceed **3.5%** of total production

## Requirements

- **Implement your solution in Python**
- Process all inspection reports in the `data/inspection_reports/` directory
- Extract defect counts from the free-text `audit_notes` fields **using an LLM integration** (note: the wording and format may vary between reports)
- Implement a `send_email()` function (a dummy/stub implementation that prints or logs the email content is acceptable)
- **Implement metrics to measure the performance of the tool itself** — specifically, how well your pipeline extracts, classifies, and processes the data (e.g., extraction accuracy, confidence scores, processing time). These metrics should be explainable to non-technical stakeholders (executives, operations managers) to support their decision-making. **Important:** These metrics evaluate the quality of the agent/tool you are building, *not* the manufacturing defect rates themselves.

### Implementation Notes

- You may use any Python libraries you find appropriate
- Code should be modular and testable
- If you need to use external API services, provide a clear configuration skeleton showing how API keys would be used, but ensure the code can run without requiring paid API access by mocking the API responses
- All parts that do not require API keys should be fully runnable
- **Important**: The provided data is only a sample. While all JSON fields will remain consistent across reports, the free text content (audit notes, descriptions, etc.) can vary significantly in format, style, and structure. Your solution should be robust and generalizable - do not overfit to the specific text patterns found in the sample reports

## What We're Looking For

- Your ability to explore and understand unfamiliar data structures
- Data extraction skills using modern techniques
- Clean, readable code
- Explainability to non-technical audiences
- Logical problem-solving approach

Good luck!

