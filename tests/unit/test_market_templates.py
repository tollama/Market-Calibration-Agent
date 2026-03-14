from features.market_templates import infer_market_template


def test_infer_market_template_detects_etf_approval() -> None:
    result = infer_market_template(
        question="Will the SEC approve a spot Solana ETF this year?",
        category="Crypto",
        slug="sec-approve-spot-solana-etf",
    )

    assert result.market_template == "etf_approval"
    assert result.template_group == "finance"


def test_infer_market_template_detects_politics_approval() -> None:
    result = infer_market_template(
        question="Will President Lee approval exceed 50% in June?",
        category="Politics",
        slug="president-lee-approval-june",
    )

    assert result.market_template == "politics_approval"
    assert result.poll_mode == "approval"


def test_infer_market_template_detects_sports_prop() -> None:
    result = infer_market_template(
        question="Will Player Z score over 25 points tonight?",
        category="Sports",
        slug="player-z-over-25-points",
    )

    assert result.market_template == "sports_player_prop"
    assert result.template_group == "sports"

