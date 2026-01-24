# Content Audit System

The audit system ensures project hygiene by detecting unused assets and enforcing limits.

## Key Concepts
- **Baseline**: A snapshot of unused assets stored in `content.lock.json`.
- **Delta**: The difference between current unused assets and the baseline.
- **Categories**: Assets are grouped into `texture`, `audio`, `data`, etc.

## Configuration
Audit policies can be configured in `config.json` under `audit_policy`.