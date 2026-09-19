import pytest
from app.scoring import ScoreComponents, calculate_bcop_score
from pydantic import ValidationError

VALID_COMPONENTS = {
    "expected_roi": 20,
    "evidence_quality": 15,
    "capital_efficiency": 12,
    "ai_leverage": 10,
    "strategic_value": 11,
    "risk": 8,
}


def test_score_sums_weighted_components() -> None:
    components = ScoreComponents(**VALID_COMPONENTS)

    assert calculate_bcop_score(components) == 76


def test_score_boundary_zero_and_maximum() -> None:
    assert calculate_bcop_score(ScoreComponents(**{field: 0 for field in ScoreComponents.model_fields})) == 0
    assert calculate_bcop_score(
        ScoreComponents(
            expected_roi=25,
            evidence_quality=20,
            capital_efficiency=15,
            ai_leverage=15,
            strategic_value=15,
            risk=10,
        )
    ) == 100


@pytest.mark.parametrize(
    ("field", "value"),
    [("expected_roi", 25.01), ("evidence_quality", -0.01), ("risk", 10.01)],
)
def test_score_rejects_out_of_range_component(field: str, value: float) -> None:
    invalid_components = {**VALID_COMPONENTS, field: value}

    with pytest.raises(ValidationError):
        ScoreComponents(**invalid_components)
