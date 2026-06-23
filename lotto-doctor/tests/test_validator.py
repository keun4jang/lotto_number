"""Tests for number validation."""

import pytest
from lotto_doctor.validator import (
    ValidationError,
    validate_number,
    validate_main_numbers,
    validate_bonus,
    validate_draw_numbers,
    is_valid_combination,
)


def test_valid_number():
    for n in [1, 22, 45]:
        validate_number(n)  # should not raise


def test_number_out_of_range():
    with pytest.raises(ValidationError):
        validate_number(0)
    with pytest.raises(ValidationError):
        validate_number(46)


def test_valid_main_numbers():
    validate_main_numbers([1, 2, 3, 4, 5, 6])


def test_main_numbers_wrong_count():
    with pytest.raises(ValidationError):
        validate_main_numbers([1, 2, 3, 4, 5])


def test_main_numbers_duplicates():
    with pytest.raises(ValidationError):
        validate_main_numbers([1, 1, 3, 4, 5, 6])


def test_main_numbers_out_of_range():
    with pytest.raises(ValidationError):
        validate_main_numbers([0, 2, 3, 4, 5, 6])


def test_valid_bonus():
    validate_bonus(7, [1, 2, 3, 4, 5, 6])


def test_bonus_in_main_numbers():
    with pytest.raises(ValidationError):
        validate_bonus(1, [1, 2, 3, 4, 5, 6])


def test_bonus_out_of_range():
    with pytest.raises(ValidationError):
        validate_bonus(46, [1, 2, 3, 4, 5, 6])


def test_validate_draw_numbers_valid():
    validate_draw_numbers([3, 7, 15, 22, 33, 44], 10)


def test_validate_draw_numbers_bonus_overlap():
    with pytest.raises(ValidationError):
        validate_draw_numbers([3, 7, 15, 22, 33, 44], 7)


def test_is_valid_combination():
    assert is_valid_combination([1, 2, 3, 4, 5, 6]) is True
    assert is_valid_combination([1, 1, 3, 4, 5, 6]) is False
    assert is_valid_combination([0, 2, 3, 4, 5, 6]) is False
