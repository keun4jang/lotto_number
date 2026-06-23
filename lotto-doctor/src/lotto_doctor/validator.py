"""Validation logic for lotto numbers."""

from __future__ import annotations


class ValidationError(Exception):
    """Raised when number validation fails."""


def validate_number(n: int) -> None:
    """Validate a single lotto number is in range 1-45."""
    if not isinstance(n, int) or not (1 <= n <= 45):
        raise ValidationError(f"Number {n!r} is out of range (1-45).")


def validate_main_numbers(numbers: list[int]) -> None:
    """Validate 6 main numbers: range 1-45 and all unique."""
    if len(numbers) != 6:
        raise ValidationError(
            f"Expected 6 main numbers, got {len(numbers)}."
        )
    for n in numbers:
        validate_number(n)
    if len(set(numbers)) != 6:
        raise ValidationError(
            f"Main numbers must be unique; got duplicates in {numbers}."
        )


def validate_bonus(bonus: int, numbers: list[int]) -> None:
    """Validate bonus number: range 1-45 and not in main numbers."""
    validate_number(bonus)
    if bonus in numbers:
        raise ValidationError(
            f"Bonus number {bonus} must not appear in main numbers {numbers}."
        )


def validate_draw_numbers(numbers: list[int], bonus: int) -> None:
    """Full validation of a draw (main numbers + bonus)."""
    validate_main_numbers(numbers)
    validate_bonus(bonus, numbers)


def is_valid_combination(numbers: list[int]) -> bool:
    """Return True if numbers form a valid 6-number lotto combination."""
    try:
        validate_main_numbers(numbers)
        return True
    except ValidationError:
        return False
