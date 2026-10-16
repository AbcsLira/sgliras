"""Pesquisa por todas as palavras, independente de ordem, acentos e caixa."""
import unicodedata


def termos_da_busca(valor):
    texto = unicodedata.normalize('NFD', str(valor or '')).lower()
    return ''.join(caractere for caractere in texto if not unicodedata.combining(caractere)).split()


def texto_corresponde_busca(texto, termos):
    normalizado = ' '.join(termos_da_busca(texto))
    return all(termo in normalizado for termo in termos)
