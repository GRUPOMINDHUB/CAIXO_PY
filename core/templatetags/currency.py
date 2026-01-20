"""
Template tags para formatação de valores monetários no padrão brasileiro.

Formata valores monetários com:
- Ponto para separar milhares (1.000,00)
- Vírgula para separar decimais
- Sempre 2 casas decimais
"""

from django import template
from decimal import Decimal

register = template.Library()


@register.filter(name='currency_br')
def currency_br(value):
    """
    Formata um valor numérico como moeda brasileira.
    
    Exemplos:
        - 1000 -> 1.000,00
        - 1000.5 -> 1.000,50
        - 1234567.89 -> 1.234.567,89
        - 100 -> 100,00
    
    Args:
        value: Valor numérico (Decimal, float, int ou string)
        
    Returns:
        String formatada no padrão brasileiro (1.000,00)
    """
    if value is None:
        return "0,00"
    
    # Converte para Decimal para garantir precisão
    try:
        if isinstance(value, str):
            value = value.replace(',', '.')
        decimal_value = Decimal(str(value))
    except (ValueError, TypeError, AttributeError):
        return "0,00"
    
    # Formata com 2 casas decimais no padrão brasileiro
    # Usa locale brasileiro ou formatação manual
    
    # Garante que temos 2 casas decimais
    decimal_value = decimal_value.quantize(Decimal('0.01'))
    
    # Converte para string e separa parte inteira e decimal
    value_str = str(decimal_value)
    
    # Verifica se é negativo
    is_negative = decimal_value < 0
    if is_negative:
        value_str = value_str[1:]  # Remove o sinal negativo temporariamente
    
    # Separa parte inteira e decimal
    if '.' in value_str:
        integer_str, decimal_str = value_str.split('.')
    else:
        integer_str = value_str
        decimal_str = '00'
    
    # Garante 2 dígitos decimais
    decimal_str = decimal_str[:2].ljust(2, '0')
    
    # Formata a parte inteira com pontos como separador de milhares
    # Adiciona pontos de mil em mil da direita para a esquerda
    integer_formatted = ''
    for i, digit in enumerate(reversed(integer_str)):
        if i > 0 and i % 3 == 0:
            integer_formatted = '.' + integer_formatted
        integer_formatted = digit + integer_formatted
    
    # Adiciona sinal negativo se necessário
    if is_negative:
        integer_formatted = '-' + integer_formatted
    
    return f"{integer_formatted},{decimal_str}"
