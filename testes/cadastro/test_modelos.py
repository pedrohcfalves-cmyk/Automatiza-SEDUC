"""Testes rápidos (sem navegador) da validação dos dados e dos bancos."""

import pytest

from automacoes.cadastro.bancos import resolver_banco
from automacoes.cadastro.modelos import Lote, cpf_confere, limpar, lote_de_linha, lotes_de_texto


@pytest.mark.parametrize("valor, codigo", [
    ("1", "001"), ("001", "001"), ("341", "341"), ("Itaú", "341"),
    ("banco do brasil", "001"), ("Banco de Brasília", "070"), ("C6 Bank", "336"),
    ("Caixa Econômica Federal", "104"), ("xyz", ""), ("", ""),
])
def test_resolver_banco(valor, codigo):
    assert resolver_banco(valor) == codigo


def test_limpar_campos():
    assert limpar("cpf", "123.456.789-09") == "12345678909"
    assert limpar("cpf", "1234567890") == "01234567890"  # zero comido pelo Excel
    assert limpar("conta", "12.345-6") == "12.345-6"
    assert limpar("nome", "  Maria  ") == "Maria"


@pytest.mark.parametrize("campo, valor, esperado", [
    ("conta", "12345-X", "12345-X"),
    ("conta", "12.345-x", "12.345-X"),  # minúscula vira maiúscula; ponto e traço ficam
    ("conta", " 1234 5-6 ", "12345-6"),  # espaços saem
    ("conta", "0012345-P", "0012345-P"),  # dígito verificador com qualquer letra
    ("conta", "ABC.12-3", "ABC.12-3"),
    ("agencia", "1234-X", "1234-X"),
    ("agencia", "3456-7", "3456-7"),
    ("agencia", "0012", "0012"),
    ("conta", "12/345_6", "123456"),  # símbolos que não são traço nem ponto saem
    ("conta", "X", "X"),
    ("conta", "", ""),
])
def test_agencia_e_conta_aceitam_letras_numeros_traco_e_ponto(campo, valor, esperado):
    assert limpar(campo, valor) == esperado


def test_cpf_continua_so_digitos():
    assert limpar("cpf", "529.982.247-2X") == "05299822472"  # o X não entra no CPF


def test_lote_de_linha_com_x():
    lote = lote_de_linha("529.982.247-25,Maria,001,1234-X,56.789-x")
    assert (lote.agencia, lote.conta) == ("1234-X", "56.789-X")


def test_lote_de_linha_separadores():
    esperado = Lote("52998224725", "Maria", "001", "1234", "56789")

    for linha in ("529.982.247-25,Maria,BB,1234, 56789 ",
                  "52998224725;Maria;001;1234;56789",
                  "52998224725\tMaria\t1\t1234\t56789"):
        assert lote_de_linha(linha) == esperado


@pytest.mark.parametrize("linha, motivo", [
    ("1,2,3", "esperado 5"),
    ("52998224725,Maria,Banco X,1,2", "banco não reconhecido"),
    ("52998224725,,001,1,2", "campos vazios"),
    ("123456789012,Maria,001,1,2", "11 dígitos"),
])
def test_lote_de_linha_invalido(linha, motivo):
    with pytest.raises(ValueError, match=motivo):
        lote_de_linha(linha)


def test_lotes_de_texto_ignora_cabecalho_e_reporta_erros():
    lotes, ignoradas = lotes_de_texto(
        "CPF;Nome;Banco;Agência;Conta\n"
        "52998224725;Maria;001;1;2\n"
        "\n"
        "1;2\n"
    )
    assert len(lotes) == 1
    assert ignoradas == [(4, "esperado 5 campos, encontrado 2")]


def test_cpf_confere():
    assert cpf_confere("52998224725")
    assert not cpf_confere("52998224724")
    assert not cpf_confere("11111111111")
    assert not cpf_confere("123")
