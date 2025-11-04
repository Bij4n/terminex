"""The 25 most-traded currencies per the BIS 2022 triennial FX survey."""

from __future__ import annotations

# (code, display name) in rough order of average daily FX turnover share.
TOP_25: list[tuple[str, str]] = [
    ("USD", "US Dollar"),
    ("EUR", "Euro"),
    ("JPY", "Japanese Yen"),
    ("GBP", "British Pound"),
    ("CNY", "Chinese Yuan"),
    ("AUD", "Australian Dollar"),
    ("CAD", "Canadian Dollar"),
    ("CHF", "Swiss Franc"),
    ("HKD", "Hong Kong Dollar"),
    ("SGD", "Singapore Dollar"),
    ("SEK", "Swedish Krona"),
    ("KRW", "South Korean Won"),
    ("NOK", "Norwegian Krone"),
    ("NZD", "New Zealand Dollar"),
    ("INR", "Indian Rupee"),
    ("MXN", "Mexican Peso"),
    ("TWD", "Taiwan Dollar"),
    ("ZAR", "South African Rand"),
    ("BRL", "Brazilian Real"),
    ("DKK", "Danish Krone"),
    ("PLN", "Polish Zloty"),
    ("THB", "Thai Baht"),
    ("ILS", "Israeli Shekel"),
    ("IDR", "Indonesian Rupiah"),
    ("CZK", "Czech Koruna"),
]

CODES: list[str] = [code for code, _ in TOP_25]
NAMES: dict[str, str] = dict(TOP_25)
