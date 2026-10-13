from app.content import _model_cost_cny_fen


def test_model_budget_cost_uses_provider_rates_and_token_volume() -> None:
    assert _model_cost_cny_fen("qwen", 0, 0) == 1
    assert _model_cost_cny_fen("qwen", 1_000_000, 0) == 200
    assert _model_cost_cny_fen("qwen", 0, 1_000_000) == 800
    assert _model_cost_cny_fen("deepseek", 1_000_000, 0) == 400
    assert _model_cost_cny_fen("deepseek", 0, 1_000_000) == 1_600
