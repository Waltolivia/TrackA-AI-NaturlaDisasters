import pytest

from intercoder_reliability.agreement import (
    cohen_kappa,
    krippendorff_alpha,
    percent_agreement,
)

CATEGORIES = [0, 1, 2]


def test_percent_agreement_counts_matches() -> None:
    assert percent_agreement([(0, 0), (1, 1), (2, 2)]) == 1.0
    assert percent_agreement([(0, 0), (0, 0), (0, 1), (1, 1)]) == 0.75
    assert percent_agreement([]) is None


def test_perfect_agreement_is_one_for_every_statistic() -> None:
    pairs = [(0, 0), (1, 1), (2, 2)]
    assert cohen_kappa(pairs, categories=CATEGORIES) == pytest.approx(1.0)
    assert cohen_kappa(pairs, categories=CATEGORIES, weights="quadratic") == pytest.approx(
        1.0
    )
    assert krippendorff_alpha(pairs, level="ordinal", categories=CATEGORIES) == (
        pytest.approx(1.0)
    )


def test_two_category_example_matches_hand_calculation() -> None:
    pairs = [(0, 0), (0, 0), (0, 1), (1, 1)]
    assert cohen_kappa(pairs, categories=[0, 1]) == pytest.approx(0.5)
    assert krippendorff_alpha(pairs, level="nominal", categories=[0, 1]) == pytest.approx(
        8 / 15
    )
    assert krippendorff_alpha(pairs, level="ordinal", categories=[0, 1]) == pytest.approx(
        8 / 15
    )


def test_three_category_example_matches_hand_calculation() -> None:
    pairs = [(0, 0), (1, 1), (2, 2), (0, 2)]
    assert cohen_kappa(pairs, categories=CATEGORIES) == pytest.approx(7 / 11)
    assert cohen_kappa(
        pairs, categories=CATEGORIES, weights="quadratic"
    ) == pytest.approx(5 / 13)
    assert krippendorff_alpha(
        pairs, level="ordinal", categories=CATEGORIES
    ) == pytest.approx(5 / 12)


def test_nominal_and_ordinal_alpha_differ_on_mixed_disagreements() -> None:
    pairs = [(0, 1), (1, 2), (0, 0), (2, 2)]
    assert cohen_kappa(pairs, categories=CATEGORIES) == pytest.approx(3 / 11)
    assert cohen_kappa(
        pairs, categories=CATEGORIES, weights="quadratic"
    ) == pytest.approx(9 / 13)
    nominal = krippendorff_alpha(pairs, level="nominal", categories=CATEGORIES)
    ordinal = krippendorff_alpha(pairs, level="ordinal", categories=CATEGORIES)
    assert nominal == pytest.approx(1 / 3)
    assert ordinal == pytest.approx(17 / 24)
    assert ordinal > nominal


def test_undefined_statistics_return_none() -> None:
    assert cohen_kappa([], categories=CATEGORIES) is None
    assert krippendorff_alpha([], level="ordinal", categories=CATEGORIES) is None
    # Every coder used a single category, so chance agreement is perfect.
    assert cohen_kappa([(1, 1), (1, 1)], categories=CATEGORIES) is None
    assert krippendorff_alpha([(1, 1), (1, 1)], level="ordinal", categories=CATEGORIES) is None


def test_krippendorff_supports_more_than_two_coders() -> None:
    assert krippendorff_alpha(
        [[0, 0, 0], [1, 1, 1]], level="nominal", categories=CATEGORIES
    ) == pytest.approx(1.0)
    assert krippendorff_alpha(
        [[0, 1], [1, 0]], level="nominal", categories=CATEGORIES
    ) == pytest.approx(-0.5)


def test_invalid_arguments_raise() -> None:
    with pytest.raises(ValueError):
        cohen_kappa([(0, 1)], categories=CATEGORIES, weights="cubic")
    with pytest.raises(ValueError):
        krippendorff_alpha([(0, 1)], level="ratio", categories=CATEGORIES)
