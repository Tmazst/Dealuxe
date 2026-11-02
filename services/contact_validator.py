"""Normalize registration phone contacts to international E.164 form."""
import re


class ContactValidationError(ValueError):
    """Raised when a phone contact cannot be safely internationalized."""


class ContactValidator:
    """Validate a phone number and ensure it has a country calling code."""

    COUNTRY_CALLING_CODES = {
        'eswatini': '268',
        'south africa': '27',
        'lesotho': '266',
        'mozambique': '258',
        'namibia': '264',
        'botswana': '267',
        'zimbabwe': '263',
        'malawi': '265',
    }

    @classmethod
    def normalize_phone(cls, phone, country=None):
        """Return a normalized +<country-code><national-number> contact.

        National numbers require a selected supported country. International
        numbers may be supplied with + or the international 00 prefix; when a
        country is selected, its calling code must match the number.
        """
        raw = str(phone or '').strip()
        if not raw:
            raise ContactValidationError('Enter a phone number.')
        if not re.fullmatch(r'[+0-9\s().-]+', raw):
            raise ContactValidationError('Use digits and standard phone-number separators only.')

        compact = re.sub(r'[\s().-]', '', raw)
        if compact.startswith('00'):
            compact = '+' + compact[2:]
        country_key = str(country or '').strip().lower()
        country_code = cls.COUNTRY_CALLING_CODES.get(country_key)

        if compact.startswith('+'):
            digits = compact[1:]
            if not digits.isdigit():
                raise ContactValidationError('Enter a valid international phone number.')
            if country_code and not digits.startswith(country_code):
                raise ContactValidationError(
                    f'The phone number country code does not match {country}.'
                )
        else:
            digits = compact
            if not digits.isdigit():
                raise ContactValidationError('Enter a valid phone number.')
            if not country_code:
                raise ContactValidationError(
                    'Choose a supported country or enter the number with its + country code.'
                )
            # Accept a number already containing the selected calling code.
            if digits.startswith(country_code) and len(digits) > len(country_code) + 7:
                pass
            else:
                # Drop the national trunk prefix (for example, 0 in 076...).
                if digits.startswith('0'):
                    digits = digits[1:]
                digits = country_code + digits

        if not digits.isdigit() or not 8 <= len(digits) <= 15:
            raise ContactValidationError(
                'Enter a valid phone number including its country code.'
            )
        return '+' + digits

    @classmethod
    def to_openwa_chat_id(cls, phone, country=None):
        """Convert a validated international number to OpenWA's chat ID form."""
        normalized = cls.normalize_phone(phone, country)
        return normalized[1:] + '@c.us'
