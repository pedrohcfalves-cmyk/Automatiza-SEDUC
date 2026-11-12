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


_MILHAR = re.compile(r"[1-9]\d{0,2}(\.\d{3})+")


def _decimal_em_texto(texto: str) -> str:
    """'1.105,50'->'1105.50'; '7.243'->'7243'; ambíguo ('1105.50') -> ValueError."""
    if "," in texto:
        return texto.replace(".", "").replace(",", ".")
    if "." in texto:
        if _MILHAR.fullmatch(texto):
            return texto.replace(".", "")
        raise ValueError(f"Valor ambíguo: '{texto}'. Use vírgula nos centavos (exemplo: 1.105,50).")
    return texto


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
    return float(_decimal_em_texto(valor))


def digitar_valor_conferido(pagina, campo, valor_padronizado, tentativas=3, espera_ms=300, antes_ms=0):
    """
    Limpa o campo de valor do SIGEF, digita, lê de volta e compara. Lança RuntimeError se não bater.

    Campo de valor de pagamento -- um erro aqui é grave. Dois cuidados:
      1) O campo é LIMPO antes de cada tentativa (seleciona tudo e apaga): press_sequentially()
         digita em cima do que já estiver lá e CONCATENARIA com o valor anterior.
      2) Compara o VALOR numérico (normalizar), não o texto: o SIGEF devolve "3.258,50",
         que nunca seria igual, letra a letra, ao valor_padronizado só-dígitos ("325850").
    `antes_ms`: espera antes de cada tentativa (a tela que recarrega e apaga o que foi digitado).
    """
    esperado = normalizar(valor_padronizado)
    ultimo = ""
    for _ in range(tentativas):
        if antes_ms:
            pagina.wait_for_timeout(antes_ms)
        campo.click()
        campo.press("Control+A")
        campo.press("Backspace")
        campo.press_sequentially(valor_padronizado, delay=20)
        pagina.wait_for_timeout(espera_ms)
        ultimo = campo.input_value().strip()
        try:
            if ultimo and abs(normalizar(ultimo) - esperado) < 0.001:
                return ultimo
        except ValueError:
            pass
    raise RuntimeError(
        f"O valor no SIGEF ficou '{ultimo}' em vez de {valor_padronizado}. "
        "Nada foi confirmado; confira o campo e tente de novo."
    )


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
        decimal = _decimal_em_texto(texto)  # fora do try: a mensagem de "ambíguo" chega a quem digitou
        try:
            centavos = round(float(decimal) * 100)
        except ValueError:
            raise ValueError(f"Valor inválido: '{valor}' (exemplo: 1.105,50).")
    if centavos < 0:
        raise ValueError(f"Valor negativo: '{valor}'.")
    inteiro, cent = divmod(centavos, 100)
    return str(centavos), f"{inteiro:,}".replace(",", ".") + f",{cent:02d}"


# O que pertence a UM processo (o resto -- escola, contas, CNPJ... -- é reaproveitado no próximo).
CHAVES_DO_PROCESSO = ("lancamentos", "ce", "ob", "grupos_ce", "lancamentos_ob", "avisos_download", "download_completo")


def sessao_ao_trocar_de_processo(sessao: dict, novo_processo: str) -> dict:
    """
    Devolve a sessão sem os dados do processo anterior, se o processo mudou.
    Sem isso, o processo novo "herdaria" NL/PP/OB do anterior quando valor e NE coincidem.
    Compara só os dígitos: o mesmo processo com e sem pontuação é o mesmo.
    """
    antigo, novo = (sessao.get("processo") or "").strip(), (novo_processo or "").strip()
    if not antigo or antigo == novo or (so_digitos(antigo) and so_digitos(antigo) == so_digitos(novo)):
        return sessao
    return {k: v for k, v in sessao.items() if k not in CHAVES_DO_PROCESSO}
