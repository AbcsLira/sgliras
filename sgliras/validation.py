"""Validação de dados recebidos; erros de entrada não são erros internos."""
from datetime import date
from decimal import Decimal, InvalidOperation
import math
from flask import request


class ValidationError(ValueError):
    pass


def json_object():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise ValidationError('Envie os dados como um objeto JSON válido.')
    return value


def text(value, label, required=True):
    if value is None and not required:
        return ''
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValidationError(f'{label} deve ser um texto' + (' não vazio.' if required else '.'))
    return value.strip()


def number(value, label, minimum=None, integer=False):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValidationError(f'{label} deve ser um número válido.')
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValidationError(f'{label} deve ser um número válido.') from None
    if not math.isfinite(result) or (integer and not result.is_integer()):
        raise ValidationError(f'{label} deve ser um número' + (' inteiro' if integer else '') + ' finito.')
    if minimum is not None and result < minimum:
        raise ValidationError(f'{label} deve ser maior ou igual a {minimum}.')
    if integer:
        try:
            exact = Decimal(str(value))
        except InvalidOperation:
            raise ValidationError(f'{label} deve ser um número inteiro válido.') from None
        if exact != exact.to_integral_value() or not -(2**63) <= exact <= 2**63 - 1:
            raise ValidationError(f'{label} deve ser um inteiro dentro do intervalo suportado.')
        return int(exact)
    return result


def iso_date(value, label):
    if not isinstance(value, str):
        raise ValidationError(f'{label} deve ser uma data válida (AAAA-MM-DD).')
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValidationError(f'{label} deve ser uma data válida (AAAA-MM-DD).') from None
    if parsed.isoformat() != value:
        raise ValidationError(f'{label} deve usar AAAA-MM-DD.')
    return value
