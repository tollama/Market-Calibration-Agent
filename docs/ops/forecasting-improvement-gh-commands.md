# Forecasting Improvement GH Commands

This repo now includes a helper script for creating the forecasting epic and the 12 child issues in dependency order.

## Files

- [scripts/github/create_forecasting_issues.sh](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/scripts/github/create_forecasting_issues.sh)
- [docs/ops/forecasting-improvement-github-issues.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/forecasting-improvement-github-issues.md)

## Preview Commands

```bash
bash scripts/github/create_forecasting_issues.sh preview
```

This prints the exact `gh issue create` commands and the temporary body-file paths it will use.

## Execute Commands

```bash
bash scripts/github/create_forecasting_issues.sh --execute
```

The script targets `tollama/Market-Calibration-Agent` by default. To override:

```bash
GITHUB_REPO=owner/repo bash scripts/github/create_forecasting_issues.sh --execute
```

## Notes

- The script requires `gh` to be installed and authenticated.
- The script does not add issue dependency links automatically after creation.
- The canonical long-form issue bodies remain in [docs/ops/forecasting-improvement-github-issues.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/forecasting-improvement-github-issues.md).
