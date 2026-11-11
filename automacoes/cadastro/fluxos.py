"""Orquestração: percorre os lotes (digitados ou da planilha) e registra o resultado.

Independe da interface: o terminal e a janela acompanham a execução por meio de
um `Relator`, e a conferência manual chega pela função `perguntar`. Quando
recebe uma `Sessao`, anota o tempo de cada item para as estatísticas.

O `Resumo` guarda em memória os itens que deram erro (`falhas`), para que a
interface possa oferecer refazer só esses itens ao fim da execução.
"""

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

from .automacao import (
    Confirmador,
    Perguntar,
    descrever_erro,
    fechar_popups,
    navegador_fechado,
    processar_lote,
)
from .config import PREFIXO
from .estatisticas import VALIDACAO, Sessao
from .log import logger
from .modelos import ROTULOS, Lote, PularLote, ReiniciarLote
from .navegador import ErroNavegador, Navegador
from .planilha import Planilha

PULADO = "pelo usuário"


class Relator:
    """Acompanha a execução; a interface sobrescreve o que lhe interessa."""

    def inicio(self, chave: int, lote: Lote, atual: int, total: int) -> None:
        """Começou o lote `chave` (nº do lote ou linha da planilha)."""

    def resultado(self, chave: int, lote: Lote, status: str, texto: str) -> None:
        """Terminou o lote: status OK | JA | ERRO | PULADO e o texto do diagnóstico."""

    def aviso(self, texto: str) -> None:
        """Mensagem complementar (problema ao gravar na planilha, por exemplo)."""

    def corrigir(self, lote: Lote) -> bool:
        """Edita o lote reprovado na conferência; False pula o lote."""
        return False

    def cancelado(self) -> bool:
        """True interrompe a execução antes do próximo lote."""
        return False


@dataclass
class Resumo:
    contagem: dict = field(default_factory=lambda: dict.fromkeys(PREFIXO, 0))
    falhas: list = field(default_factory=list)  # [(chave, Lote)] dos itens com ERRO

    def registrar(self, chave: int, lote: Lote, status: str) -> None:
        self.contagem[status] += 1

        if status == "ERRO":
            self.falhas.append((chave, lote))

    def __str__(self) -> str:
        c = self.contagem
        return (f"{c['OK']} ok, {c['JA']} já cadastrados, "
                f"{c['PULADO']} pulados, {c['ERRO']} erros")


class _Medicao:
    """Tempo de um item, separando o tempo de máquina do tempo de pessoas."""

    def __init__(self):
        self.inicio = time.perf_counter()
        self.espera = 0.0
        self.caminho = ""

    def anotar(self, confirmador: Confirmador) -> None:
        self.espera += confirmador.espera
        self.caminho = confirmador.caminho or self.caminho

    @contextmanager
    def pausa(self):
        """Conta como espera o tempo em que uma pessoa está corrigindo dados."""
        inicio = time.perf_counter()
        try:
            yield
        finally:
            self.espera += time.perf_counter() - inicio

    def registrar(self, sessao: Optional[Sessao], status: str, mensagem: str,
                  caminho: str = "") -> None:
        if sessao is not None:
            sessao.registrar(status, caminho or self.caminho or "desconhecido",
                             time.perf_counter() - self.inicio, self.espera, mensagem)


@contextmanager
def _encerrando(sessao: Optional[Sessao], relator: "Relator"):
    """Fecha a sessão de estatística mesmo se a execução parar no meio."""
    try:
        yield
    except BaseException:
        if sessao is not None:
            sessao.encerrar(interrompida=True)
        raise
    else:
        if sessao is not None:
            sessao.encerrar(interrompida=relator.cancelado())


def _executar(navegador: Navegador, lote: Lote, confirmador: Confirmador) -> tuple:
    """Processa um lote tratando falhas; ReiniciarLote sobe para quem chamou."""
    page = navegador.page

    try:
        return processar_lote(page, lote, confirmador)

    except PularLote:
        return "PULADO", PULADO

    except ReiniciarLote:
        raise

    # Timeout ou qualquer outra falha: desiste deste lote e segue para o próximo
    except Exception as erro:
        if navegador_fechado(page):
            raise ErroNavegador("O navegador foi fechado durante o cadastro.") from erro

        return "ERRO", descrever_erro(erro)

    finally:
        if not navegador_fechado(page):
            fechar_popups(navegador.context, page)


def executar_lotes(navegador: Navegador, lotes: Sequence[Lote], relator: Relator,
                   perguntar: Optional[Perguntar] = None,
                   sessao: Optional[Sessao] = None,
                   numeros: Optional[Sequence[int]] = None) -> Resumo:
    """Modo lote: dados digitados, colados ou lidos de um arquivo.

    `numeros` mantém a numeração original ao refazer só os itens com erro.
    """
    navegador.garantir()
    resumo, total = Resumo(), len(lotes)
    numeros = numeros or range(1, total + 1)

    with _encerrando(sessao, relator):
        for atual, (numero, lote) in enumerate(zip(numeros, lotes), 1):
            if relator.cancelado():
                break

            medicao = _Medicao()

            while True:
                relator.inicio(numero, lote, atual, total)
                confirmador = Confirmador(perguntar)

                try:
                    status, mensagem = _executar(navegador, lote, confirmador)
                except ReiniciarLote:
                    with medicao.pausa():
                        corrigido = relator.corrigir(lote)

                    if corrigido:
                        continue

                    status, mensagem = "PULADO", PULADO
                finally:
                    medicao.anotar(confirmador)

                break

            medicao.registrar(sessao, status, mensagem)
            resumo.registrar(numero, lote, status)
            relator.resultado(numero, lote, status, PREFIXO[status] + mensagem)

    logger.info("Resumo: %s", resumo)
    return resumo


def executar_planilha(navegador: Navegador, planilha: Planilha, colunas: dict,
                      linhas: Iterable[int], coluna_resultado: str,
                      relator: Relator, perguntar: Optional[Perguntar] = None,
                      sessao: Optional[Sessao] = None) -> Resumo:
    """Modo planilha: lê o Excel e devolve o diagnóstico em cada linha.

    `linhas` é o intervalo escolhido (`range(primeira, final + 1)`) ou só as
    linhas que deram erro, quando a pessoa pede para refazê-las. Cada linha é
    lida de novo do Excel, então correções feitas na planilha são aproveitadas.
    """
    navegador.garantir()
    linhas = list(linhas)
    resumo, total = Resumo(), len(linhas)

    with _encerrando(sessao, relator):
        for atual, linha in enumerate(linhas, 1):
            if relator.cancelado():
                break

            medicao = _Medicao()
            lote, banco_bruto = planilha.ler_lote(linha, colunas)
            faltando = lote.faltando()

            if len(faltando) == len(ROTULOS) and not banco_bruto:  # linha vazia
                continue

            relator.inicio(linha, lote, atual, total)
            caminho = VALIDACAO

            if banco_bruto and not lote.banco:
                status, mensagem = "ERRO", f"banco não reconhecido - {banco_bruto}"
            elif faltando:
                status, mensagem = "ERRO", "campos vazios - " + ", ".join(faltando)
            elif not lote.cpf_valido():
                status, mensagem = "ERRO", "CPF deve ter 11 dígitos"
            else:
                confirmador = Confirmador(perguntar, editavel=False)

                try:
                    status, mensagem = _executar(navegador, lote, confirmador)
                finally:
                    medicao.anotar(confirmador)

                caminho = ""

            texto = PREFIXO[status] + mensagem
            gravacao = planilha.gravar(linha, texto, coluna_resultado)

            medicao.registrar(sessao, status, mensagem, caminho)
            resumo.registrar(linha, lote, status)
            relator.resultado(linha, lote, status, texto)

            for aviso in gravacao.avisos:
                relator.aviso(aviso)

    logger.info("Resumo: %s", resumo)
    return resumo
