"""
Dinheiro, mês e documentos -- as conversões usadas em todo o programa.

Fica separado do utils.py porque não depende do Playwright nem do PyMuPDF:
o formulário de dados, o modo treino e os testes usam sem abrir navegador.
(O utils.py continua oferecendo as mesmas funções, para quem já as usava.)

Copyright (c) 2026 Pedro Henrique Carpina Farias Alves. Todos os direitos reservados. Ver LICENSE.
"""
import re


def so_digitos(texto) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def normalizar(valor) -> float:
    """
    Converte qualquer um dos formatos de valor do projeto para float em reais:

    79054      (valor_padronizado, sem vírgula)   -> 790.54
    790,54     (como aparece no SIGEF)            -> 790.54
    1.234,56   (com separador de milhar)          -> 1234.56
    """
    valor = str(valor).replace("R$", "").strip()
    if valor.isdigit():
        return float(valor) / 100
    return float(valor.replace(".", "").replace(",", "."))


def reais(valor: float) -> str:
    """1234.5 -> '1.234,50' (o jeito que se escreve dinheiro no Brasil)."""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def padronizar_mes(mes) -> str:
    """
    Aceita o mês em qualquer formato ("1", "01", "9", "13"...) e devolve SEM
    zero à esquerda -- é o formato do <option value> do combo do SIGEF
    (#cboMesComp); um "09" faz o select_option travar. 13 = Décimo Terceiro.

    Lança ValueError se não for um número de 1 a 13.
    """
    texto = str(mes).strip()
    if not texto.isdigit():
        raise ValueError(f"Mês de referência inválido: '{mes}' (escolha um mês de 1 a 12, ou 13 = Décimo Terceiro).")
    numero = int(texto)
    if not 1 <= numero <= 13:
        raise ValueError(f"Mês de referência fora do intervalo 1-13: '{mes}' (13 = Décimo Terceiro).")
    return str(numero)


def padronizar_valor(valor) -> tuple[str, str]:
    """
    Aceita um valor em reais em qualquer formato do projeto:

        "1.105,50"   "1105,50"   "1105,5"   "110550" (só dígitos: 2 últimos = centavos)

    e devolve os DOIS formatos usados no projeto:

        valor_padronizado -> só dígitos, 2 últimos = centavos (ex: "110550")
        valor_formatado   -> em R$ (ex: "1.105,50")

    Lança ValueError se o texto não puder ser lido como valor.
    """
    texto = str(valor).replace("R$", "").strip()
    if not texto:
        raise ValueError("Valor em branco.")
    if texto.isdigit():
        centavos = int(texto)
    else:
        try:
            centavos = round(float(texto.replace(".", "").replace(",", ".")) * 100)
        except ValueError:
            raise ValueError(f"Valor inválido: '{valor}' (exemplo: 1.105,50).")
    if centavos < 0:
        raise ValueError(f"Valor negativo: '{valor}'.")
    inteiro, cent = divmod(centavos, 100)
    return str(centavos), f"{inteiro:,}".replace(",", ".") + f",{cent:02d}"

