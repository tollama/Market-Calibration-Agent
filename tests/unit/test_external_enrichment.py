from pathlib import Path

import pandas as pd

from features.external_enrichment import ExternalEnrichmentConfig, enrich_with_external_features


def test_enrich_with_external_features_uses_local_csv_inputs(tmp_path: Path) -> None:
    news_path = tmp_path / "news.csv"
    polls_path = tmp_path / "polls.csv"
    news_path.write_text(
        "\n".join(
            [
                "headline,published_at",
                "Candidate A gains support,2026-01-01T00:30:00Z",
                "Unrelated story,2026-01-01T00:15:00Z",
            ]
        ),
        encoding="utf-8",
    )
    polls_path.write_text(
        "\n".join(
            [
                "question,subject,yes_support,no_support,published_at",
                "Candidate A election,Candidate A,52,48,2026-01-01T00:00:00Z",
            ]
        ),
        encoding="utf-8",
    )

    rows = pd.DataFrame(
        [
            {
                "snapshot_ts": "2026-01-01T01:00:00Z",
                "query_terms": ["candidate", "candidate a"],
            }
        ]
    )

    enriched = enrich_with_external_features(
        rows,
        ExternalEnrichmentConfig(
            news_csv_path=str(news_path),
            polls_csv_path=str(polls_path),
        ),
    )

    assert enriched["news_articles_24h"].iloc[0] == 1.0
    assert enriched["poll_count_30d"].iloc[0] == 1.0
    assert enriched["poll_yes_support"].iloc[0] == 52.0

