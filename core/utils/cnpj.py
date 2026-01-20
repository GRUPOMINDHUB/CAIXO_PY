"""
Módulo de validação e formatação de CNPJ.

Implementa validação rigorosa de CNPJ conforme a Receita Federal do Brasil.
"""

import re
from typing import Optional


def clean_cnpj(cnpj: str) -> str:
    """
    Remove caracteres não numéricos do CNPJ.
    
    Args:
        cnpj: String contendo CNPJ com ou sem formatação
        
    Returns:
        String contendo apenas dígitos do CNPJ
    """
    return re.sub(r'\D', '', cnpj)


def validate_cnpj(cnpj: str) -> bool:
    """
    Valida CNPJ usando o algoritmo da Receita Federal.
    
    Verifica:
    - Formato básico (14 dígitos)
    - Dígitos verificadores
    - Rejeita CNPJs com todos os dígitos iguais
    
    Args:
        cnpj: CNPJ para validação (com ou sem formatação)
        
    Returns:
        True se o CNPJ for válido, False caso contrário
    """
    cnpj = clean_cnpj(cnpj)
    
    # Verifica se tem 14 dígitos
    if len(cnpj) != 14:
        return False
    
    # Rejeita CNPJs com todos os dígitos iguais (ex: 00000000000000)
    if cnpj == cnpj[0] * 14:
        return False
    
    # Calcula o primeiro dígito verificador
    peso = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(cnpj[i]) * peso[i] for i in range(12))
    resto = soma % 11
    digito1 = 0 if resto < 2 else 11 - resto
    
    if int(cnpj[12]) != digito1:
        return False
    
    # Calcula o segundo dígito verificador
    peso = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(cnpj[i]) * peso[i] for i in range(13))
    resto = soma % 11
    digito2 = 0 if resto < 2 else 11 - resto
    
    return int(cnpj[13]) == digito2


def format_cnpj(cnpj: str) -> str:
    """
    Formata CNPJ no padrão XX.XXX.XXX/XXXX-XX.
    
    Args:
        cnpj: CNPJ sem formatação
        
    Returns:
        CNPJ formatado ou string vazia se inválido
    """
    cnpj = clean_cnpj(cnpj)
    if len(cnpj) != 14:
        return ''
    return f'{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:14]}'


