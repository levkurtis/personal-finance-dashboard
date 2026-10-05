import pytest

from finance import config
from finance.sources import SOURCES_BY_KEY

EXAMPLE = """
[income.header_aliases]
salary_netto = ["Example Corp Salary (Netto)"]
bank_benefits = "Example Bank bonus"

[goals]
brutto_monthly_kr = 61234.5
"""


def test_defaults_without_local_file():
    assert config.local_settings() == {}
    assert config.header_aliases() == {}
    assert config.goal_brutto_monthly_ore("real") == config.DEFAULT_GOAL_BRUTTO_MONTHLY_ORE


def test_local_file_aliases_and_goal(local_config):
    local_config(EXAMPLE)
    assert config.header_aliases() == {
        "salary_netto": ["Example Corp Salary (Netto)"],
        "bank_benefits": ["Example Bank bonus"],
    }
    assert config.goal_brutto_monthly_ore("real") == 6_123_450


def test_demo_mode_never_uses_the_real_goal(local_config):
    local_config(EXAMPLE)
    assert config.goal_brutto_monthly_ore("demo") == config.DEFAULT_GOAL_BRUTTO_MONTHLY_ORE


@pytest.mark.parametrize(
    "text, call",
    [
        ("not = [valid", config.header_aliases),
        ("[income]\nheader_aliases = 3", config.header_aliases),
        ("[income.header_aliases]\nsalary_netto = [1, 2]", config.header_aliases),
        ('[goals]\nbrutto_monthly_kr = "lots"', lambda: config.goal_brutto_monthly_ore("real")),
    ],
)
def test_invalid_local_config_raises_value_error(local_config, text, call):
    local_config(text)
    with pytest.raises(ValueError):
        call()


def test_example_file_is_valid_and_contains_no_personal_names(monkeypatch):
    example = config.ROOT / "finance.local.example.toml"
    monkeypatch.setenv("FINANCE_LOCAL_CONFIG", str(example))
    aliases = config.header_aliases()
    assert set(aliases) <= set(SOURCES_BY_KEY)
    assert all(h.startswith("Example ") for headers in aliases.values() for h in headers)
    assert config.goal_brutto_monthly_ore("real") == config.DEFAULT_GOAL_BRUTTO_MONTHLY_ORE
