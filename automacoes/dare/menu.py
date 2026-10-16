"""Interface de terminal: banner, menu, perguntas com validação, resumo e mensagens."""

import os
import re
import subprocess
import sys
import textwrap
from datetime import date
from pathlib import Path

from . import config, utils
from .modelos import DadosDare, ResultadoLote

LARGURA = 66  # largura total das caixas

_USAR_COR = False
RESET, NEGRITO, DIM = "\033[0m", "\033[1m", "\033[2m"
VERMELHO, VERDE, AMARELO, CIANO = "\033[31m", "\033[32m", "\033[33m", "\033[36m"
_ANSI = re.compile(r"\033\[[0-9;]*m")


def preparar_terminal() -> None:
    """UTF-8 na saída e cores ANSI (inclusive no Windows 10+). Sem cor se não for um terminal."""
    global _USAR_COR
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if os.name == "nt":
        os.system("")  # habilita sequências ANSI no console do Windows
    _USAR_COR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _c(texto: str, *estilos: str) -> str:
    return "".join(estilos) + texto + RESET if _USAR_COR and estilos else texto


def _tamanho(texto: str) -> int:
    return len(_ANSI.sub("", texto))


def limpar() -> None:
    if _USAR_COR:
        print("\033[2J\033[H", end="")


# ---- Blocos visuais -----------------------------------------------------------------------

def banner() -> None:
    interno = LARGURA - 2
    titulo = "DARE AUTOMAÇÃO"
    sub = "gerar DARE  →  salvar PDF  →  anexar no SEI"
    print(_c("╔" + "═" * interno + "╗", CIANO))
    for texto, estilo in ((titulo, NEGRITO), (sub, DIM)):
        meio = texto.center(interno)
        print(_c("║", CIANO) + _c(meio, estilo) + _c("║", CIANO))
    print(_c("╚" + "═" * interno + "╝", CIANO))


def caixa(titulo: str, linhas: list[str], cor: str = CIANO) -> None:
    """Caixa com título; cada linha é um texto simples (quebra automática)."""
    interno = LARGURA - 4
    topo = f"┌─ {titulo} " + "─" * (LARGURA - 5 - len(titulo)) + "┐"
    print(_c(topo, cor))
    for linha in linhas:
        pedacos = textwrap.wrap(linha, interno) or [""]
        for p in pedacos:
            print(_c("│", cor) + " " + p.ljust(interno) + " " + _c("│", cor))
    print(_c("└" + "─" * (LARGURA - 2) + "┘", cor))


def caixa_campos(titulo: str, campos: list[tuple[str, str]], cor: str = CIANO) -> None:
    """Caixa de pares rótulo/valor alinhados."""
    interno = LARGURA - 4
    largura_rotulo = max(len(r) for r, _ in campos) + 2
    topo = f"┌─ {titulo} " + "─" * (LARGURA - 5 - len(titulo)) + "┐"
    print(_c(topo, cor))
    for rotulo, valor in campos:
        pedacos = textwrap.wrap(str(valor), interno - largura_rotulo) or [""]
        for i, p in enumerate(pedacos):
            esq = (rotulo + ":").ljust(largura_rotulo) if i == 0 else " " * largura_rotulo
            conteudo = _c(esq, DIM) + p
            falta = interno - _tamanho(conteudo)
            print(_c("│", cor) + " " + conteudo + " " * falta + " " + _c("│", cor))
    print(_c("└" + "─" * (LARGURA - 2) + "┘", cor))


def info(msg: str) -> None:
    print(f"  {_c('ℹ', CIANO)} {msg}")


def sucesso(msg: str) -> None:
    print(f"  {_c('✔', VERDE)} {msg}")


def aviso(msg: str) -> None:
    print(f"  {_c('⚠', AMARELO)} {msg}")


def erro(msg: str) -> None:
    print(f"  {_c('✖', VERMELHO)} {msg}")


def pausar(msg: str = "Pressione Enter para continuar...") -> None:
    input(f"\n  {_c(msg, DIM)}")


# ---- Menu principal -----------------------------------------------------------------------

def menu_principal(chrome_ok: bool) -> str:
    """Mostra o menu e devolve a opção escolhida ('1'..'4' ou '0')."""
    limpar()
    banner()
    chrome = _c("● aberto", VERDE) if chrome_ok else _c("● fechado (abre ao iniciar)", AMARELO)
    print(f"\n  Chrome de depuração (porta {config.PORTA_CDP}): {chrome}")
    print(f"  Pasta dos PDFs: {_c(str(config.PASTA_PDF), DIM)}")
    print(f"  {_c('Uso restrito a pessoas autorizadas · veja LICENCA.txt', DIM)}\n")
    opcoes = [
        ("1", "Modo em lotes     (digitar os dados na tela)"),
        ("2", "Modo planilha     (ler os dados de uma planilha do Excel)"),
        ("3", "Abrir a pasta dos PDFs"),
        ("4", "Abrir a pasta de logs"),
        ("0", "Sair"),
    ]
    for chave, texto in opcoes:
        print(f"   {_c(chave, NEGRITO, CIANO)}  {texto}")
    validas = {c for c, _ in opcoes}
    while True:
        escolha = input(f"\n  {_c('›', CIANO)} Escolha uma opção: ").strip()
        if escolha in validas:
            return escolha
        erro("Opção inválida.")


# ---- Perguntas ----------------------------------------------------------------------------

def entrada(rotulo: str, dica: str = "") -> str:
    """Pergunta simples (aceita resposta vazia). Devolve o texto digitado, sem espaços nas pontas."""
    sufixo = " " + _c(f"[{dica}]", DIM) if dica else ""
    return input(f"  {_c('›', CIANO)} {rotulo}{sufixo}: ").strip()


def _perguntar(rotulo, ajuda="", padrao="", exibir_padrao=None, validar=None):
    while True:
        if ajuda:
            print(f"     {_c(ajuda, DIM)}")
        dica = ""
        if padrao:
            dica = " " + _c(f"[Enter = {exibir_padrao or padrao}]", DIM)
        resposta = input(f"  {_c('›', CIANO)} {rotulo}{dica}: ").strip()
        valor = resposta or padrao
        if not valor:
            erro("Campo obrigatório.")
            continue
        if validar is None:
            return valor
        try:
            return validar(valor)
        except ValueError as exc:
            erro(str(exc))


def _doc(validador, nome, digitos):
    def verificar(texto):
        d = utils.somente_digitos(texto)
        if len(d) != digitos:
            raise ValueError(f"{nome} deve ter {digitos} dígitos.")
        if not validador(texto):
            raise ValueError(f"{nome} inválido (dígitos verificadores não conferem).")
        return texto.strip()

    return verificar


def _processo(texto):
    return utils.validar_processo(texto)


def _valor(texto):
    return utils.formatar_valor(texto)


def _perguntar_dados(base: DadosDare | None, repetir_pessoal: bool = True,
                     venc_padrao: date | None = None) -> DadosDare:
    """
    As perguntas de um lançamento. `base` fornece os valores padrão (Enter). Com
    repetir_pessoal=False, processo e CPF não têm padrão (cada lote tem os seus).
    """
    u = base
    pessoal = u if (u and repetir_pessoal) else None
    processo = _perguntar(
        "Processo SEI", "Número do processo que receberá o DARE.",
        padrao=pessoal.processo if pessoal else "", validar=_processo,
    )
    cnpj = _perguntar(
        "CNPJ (órgão)", "Usado para identificar o contribuinte no DARE.",
        padrao=u.cnpj if u else "", validar=_doc(utils.validar_cnpj, "CNPJ", 14),
    )
    cpf = _perguntar(
        "CPF do servidor", "",
        padrao=pessoal.cpf if pessoal else "", validar=_doc(utils.validar_cpf, "CPF", 11),
    )
    recolhedor = _perguntar(
        "CNPJ do recolhedor", "",
        padrao=u.cnpj_recolhedor if u else "", validar=_doc(utils.validar_cnpj, "CNPJ", 14),
    )
    referencia = _perguntar(
        "Mês/ano de referência", "Formato MMAAAA (ex.: 102026).",
        padrao=u.mes_ano_referencia if u else "", validar=utils.validar_mes_ano,
        exibir_padrao=utils.formatar_mes_ano(u.mes_ano_referencia) if u else None,
    )
    sugestao = venc_padrao or utils.vencimento_padrao()
    vencimento = _perguntar(
        "Data de vencimento", "DD/MM/AAAA. Padrão: 1 mês à frente, em dia útil.",
        padrao=sugestao.strftime("%d/%m/%Y"), validar=utils.ler_vencimento,
    )
    valor = _perguntar(
        "Valor (R$)", "Ex.: 100,00 — a vírgula é colocada automaticamente no site.",
        padrao=u.valor if u else config.VALOR_PADRAO, validar=_valor,
    )
    return DadosDare(processo, cnpj, cpf, recolhedor, referencia, vencimento, valor)


# ---- Lotes --------------------------------------------------------------------------------

def sim_nao(pergunta: str, padrao: bool = True) -> bool:
    dica = "[S/n]" if padrao else "[s/N]"
    resposta = input(f"\n  {_c('›', CIANO)} {pergunta} {dica}: ").strip().lower()
    if not resposta:
        return padrao
    return resposta in ("s", "sim", "y", "yes")


def _nome_lote(i: int, d: DadosDare) -> str:
    """'Lote 3' ou, vindo de planilha, 'Lote 3 (linha 9)'."""
    return f"Lote {i} ({d.origem})" if d.origem else f"Lote {i}"


def _linha_lote(i: int, d: DadosDare) -> str:
    linha = (
        f"  {i:>2}  {d.processo:<20} {utils.formatar_cpf(d.cpf):<14} "
        f"{utils.formatar_mes_ano(d.mes_ano_referencia):<7} "
        f"{d.vencimento.strftime('%d/%m/%Y'):<10} R$ {d.valor:>10}"
    )
    return linha + (_c(f"  ← {d.origem}", DIM) if d.origem else "")


def listar_lotes(lotes: list[DadosDare]) -> None:
    cab = "  #   Processo             CPF            Ref.    Vencimento   Valor"
    print(_c(cab, DIM))
    for i, d in enumerate(lotes, 1):
        print(_linha_lote(i, d))


def coletar_lotes(ultimos: DadosDare | None) -> list[DadosDare]:
    """
    Pergunta os dados de cada lote, um por vez, até você dizer que não há mais lotes.
    CNPJ, recolhedor, referência, vencimento e valor repetem o lote anterior (ou os últimos
    usados, no lote 1): é só dar Enter. Processo e CPF são sempre digitados.
    """
    lotes: list[DadosDare] = []
    while True:
        n = len(lotes) + 1
        limpar()
        banner()
        print()
        caixa(
            f"Lote {n}",
            [
                "Preencha os dados deste lote. Enter aceita o valor entre colchetes.",
                "Ctrl+C cancela e volta ao menu (os lotes digitados são descartados).",
            ],
        )
        if lotes:
            print()
            listar_lotes(lotes)
        print()
        anterior = lotes[-1] if lotes else ultimos
        lotes.append(
            _perguntar_dados(
                anterior,
                repetir_pessoal=False,
                venc_padrao=lotes[-1].vencimento if lotes else None,
            )
        )
        if not sim_nao("Adicionar outro lote?", padrao=True):
            return lotes


def _avisos_lotes(lotes: list[DadosDare]) -> list[str]:
    avisos = []
    vistos: dict[tuple, int] = {}
    for i, d in enumerate(lotes, 1):
        chave = (d.processo, utils.somente_digitos(d.cpf), d.mes_ano_referencia)
        if chave in vistos:
            avisos.append(f"Lotes {vistos[chave]} e {i} têm o mesmo processo, CPF e referência"
                          f"{' (confira se a planilha não repete a linha)' if d.origem else ''}.")
        else:
            vistos[chave] = i
        if d.vencimento < date.today():
            avisos.append(f"{_nome_lote(i, d)}: a data de vencimento está no passado.")
    return avisos


_COMANDO = re.compile(
    r"(iniciar|inicio|sim|i|s|editar|e|remover|r|adicionar|a|cancelar|c)\s*(\d+)?", re.I
)


def _numero_do_lote(numero: str | None, total: int) -> int | None:
    """Número do lote (1..total) a partir do comando; pergunta se não veio junto."""
    if numero is None and total == 1:
        return 1
    if numero is None:
        numero = input(f"  {_c('›', CIANO)} Qual lote? (1-{total}): ").strip()
    if numero.isdigit() and 1 <= int(numero) <= total:
        return int(numero)
    return None


def revisar_lotes(lotes: list[DadosDare]) -> bool:
    """
    Tela final de conferência. Mostra todos os lotes e deixa corrigir antes de executar:
    editar, remover ou adicionar um lote. Modifica `lotes` no lugar.
    Devolve True para iniciar (só com confirmação explícita) ou False para cancelar.
    """
    mensagem: tuple[str, str] | None = None
    while True:
        limpar()
        banner()
        print()
        caixa(
            "Confira todos os dados",
            [
                f"{len(lotes)} lançamento(s): cada um gera o DARE, salva o PDF e anexa no SEI.",
                "Se um lote falhar, o programa segue para o próximo e mostra o resumo no fim.",
            ],
        )
        print()
        listar_lotes(lotes)
        print(_c(f"\n  Fixos: {config.ORGAO} · receita {config.CODIGO_RECEITA} · "
                 f"UG {config.UNIDADE_GESTORA} / gestão {config.GESTAO}", DIM))
        print()
        for texto in _avisos_lotes(lotes):
            aviso(texto)
        if mensagem:
            (aviso if mensagem[0] == "aviso" else erro)(mensagem[1])
            mensagem = None
        print(f"\n  {_c('I', NEGRITO, CIANO)} iniciar    {_c('E n', NEGRITO, CIANO)} editar lote n"
              f"    {_c('R n', NEGRITO, CIANO)} remover lote n    {_c('A', NEGRITO, CIANO)} adicionar lote"
              f"    {_c('C', NEGRITO, CIANO)} cancelar")
        resposta = input(f"\n  {_c('›', CIANO)} O que deseja fazer? ").strip()
        casou = _COMANDO.fullmatch(resposta)
        if not casou:
            mensagem = ("erro", "Comando inválido. Digite I para iniciar (ou E 2, R 2, A, C).")
            continue
        comando, numero = casou.group(1).lower(), casou.group(2)

        if comando in ("i", "s", "iniciar", "inicio", "sim"):
            return True
        if comando in ("c", "cancelar"):
            return False
        if comando in ("a", "adicionar"):
            limpar()
            banner()
            print()
            caixa(f"Lote {len(lotes) + 1} (novo)", ["Enter aceita o valor entre colchetes."])
            print()
            lotes.append(_perguntar_dados(lotes[-1], False, lotes[-1].vencimento))
            continue

        n = _numero_do_lote(numero, len(lotes))
        if n is None:
            mensagem = ("erro", f"Número de lote inválido. Use de 1 a {len(lotes)}.")
            continue
        if comando in ("e", "editar"):
            limpar()
            banner()
            print()
            caixa(
                f"Editando o lote {n}",
                ["Enter mantém o valor entre colchetes; digite só o que quer corrigir."],
            )
            print()
            atual = lotes[n - 1]
            lotes[n - 1] = _perguntar_dados(atual, True, atual.vencimento)
            lotes[n - 1].origem = atual.origem  # continua sabendo de qual linha da planilha veio
        else:  # remover
            if len(lotes) == 1:
                mensagem = ("aviso", "Este é o único lote. Para desistir, use C (cancelar).")
            elif sim_nao(f"Remover o lote {n} ({lotes[n - 1].processo})?", padrao=False):
                del lotes[n - 1]
                mensagem = ("aviso", f"Lote {n} removido.")


def cabecalho_lote(i: int, total: int, d: DadosDare) -> None:
    """Separador que aparece no início do processamento de cada lote."""
    print()
    titulo = f"━━ Lote {i} de {total}" + (f" ({d.origem})" if d.origem else "") + " "
    print(_c(titulo + "━" * max(2, LARGURA - len(titulo)), NEGRITO, CIANO))
    print(f"  {d.processo}  ·  CPF {utils.formatar_cpf(d.cpf)}  ·  "
          f"{utils.formatar_mes_ano(d.mes_ano_referencia)}  ·  R$ {d.valor}")


def resumo_lotes(resultados: list[ResultadoLote], total: int) -> None:
    """Resumo final: o que deu certo, o que falhou e o que ficou sem processar."""
    ok = [r for r in resultados if r.sucesso]
    falhas = [r for r in resultados if not r.sucesso]
    linhas = []
    for i, r in enumerate(resultados, 1):
        nome = r.servidor or utils.formatar_cpf(r.dados.cpf)
        if r.sucesso:
            linhas.append(f"✔ {_nome_lote(i, r.dados)}: {r.dados.processo} · {nome}")
        else:
            linhas.append(f"✖ {_nome_lote(i, r.dados)}: {r.dados.processo} · {nome}")
            linhas.append(f"   ↳ {r.erro}")
            if r.pdf:
                linhas.append(f"   ↳ O DARE foi gerado, mas não anexado: {r.pdf}")
    restantes = total - len(resultados)
    if restantes:
        linhas.append(f"… {restantes} lote(s) não chegaram a ser processados.")
    linhas.append("")
    linhas.append(f"Concluídos: {len(ok)} · Com erro: {len(falhas)} · Total: {total}")
    linhas.append(f"PDFs em: {config.PASTA_PDF}")
    print()
    caixa("Resumo dos lotes", linhas, cor=VERDE if not falhas and not restantes else AMARELO)


def aguardar_login() -> None:
    print()
    caixa(
        "Antes de continuar",
        [
            "1. Na aba do DARE e na aba do SEI, entre com a sua conta.",
            "2. Quando as duas estiverem logadas, volte aqui.",
            "O script troca de aba sozinho; não precisa deixar nenhuma em foco.",
        ],
        cor=AMARELO,
    )
    pausar("Pressione Enter quando estiver logado nos dois sistemas...")
    print()


# ---- Pastas -------------------------------------------------------------------------------

def abrir_pasta(pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    try:
        if os.name == "nt":
            os.startfile(pasta)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(pasta)], check=False)
        else:
            subprocess.run(["xdg-open", str(pasta)], check=False)
        sucesso(f"Pasta aberta: {pasta}")
    except Exception as exc:  # noqa: BLE001
        erro(f"Não consegui abrir a pasta ({exc}). Caminho: {pasta}")
