"""
O Cadastro de Credores (credor pessoa física + domicílio bancário no SIGEF) dentro da janela.

A automação é a do programa "Cadastrar_Pessoas_e_conta" (CadastroSIGEF), sem mudança de regra,
em automacoes/cadastro/. Aqui fica só o que a janela Tkinter dele (sigef/interface/) fazia por
cima do núcleo, agora respondendo à página da Central (janela/interface/cadastro.js), com as
mesmas telas e na mesma ordem:

    Início -> 1 Entrar no SIGEF -> 2 Escolher os dados (planilha do Excel ou digitar/colar)
           -> 3 Cadastrar -> 4 Ver o resultado          (+ Estatísticas, Ajuda)

A página chama tudo por UMA porta, chamar(acao, dados) (Api.cadastro do app_janela), e recebe
o andamento pelos eventos "cad_*".

UMA LINHA SÓ PARA O CHROME E O EXCEL: o Playwright e o Excel (COM) só podem ser usados na linha
de execução que os criou. Como no programa original (interface/trabalhador.py), todo trabalho que
toca neles roda numa linha própria deste módulo, uma coisa de cada vez.

O QUE MUDA POR ESTAR NA CENTRAL (de propósito, como no DARE):
    - um Chrome só: abre o Chrome da Central (porta 9222, perfil C:\\ChromeAutomacao), com as
      opções dela; sem o Chrome, o programa volta ao jeito dele (procura o Edge);
    - uma automação por vez: o cadastro só começa com o USO_DO_CHROME de modulos_janela;
    - o ano do SIGEF: os endereços (SIGEF2026/...) seguem o ano escolhido no rodapé da barra lateral.
Os dados (estatísticas, registros) continuam em ~/.sigef-automacao, a pasta do programa antigo:
quem já usava encontra as sessões e as cronometragens na Central.
"""
import os
import queue
import threading
import traceback
from pathlib import Path

from automacoes import geral
from automacoes.cadastro import __version__, config, estatisticas, relatorio
from automacoes.cadastro import navegador as _navegador
from automacoes.cadastro.automacao import CONFIRMAR_DOMICILIO, INCLUIR_CREDOR
from automacoes.cadastro.bancos import descrever_banco
from automacoes.cadastro.fluxos import Relator, executar_lotes, executar_planilha
from automacoes.cadastro.log import configurar_log, logger
from automacoes.cadastro.modelos import (ROTULOS, Lote, Resposta, cpf_confere, ler_arquivo_lotes, limpar,
                                         lotes_de_texto)
from automacoes.cadastro.navegador import ErroNavegador
from automacoes.sigef_sei.preparar_navegador import PASTA_PERFIL_CHROME_AUTOMACAO
from janela import modulos_janela

# ======================================================== textos da janela original
# (sigef/interface/telas.py e dialogos.py)

PERGUNTAS = {
    INCLUIR_CREDOR: "Cadastrar esta pessoa como credor no SIGEF?",
    CONFIRMAR_DOMICILIO: "Gravar a conta bancária desta pessoa no SIGEF?",
}
DICAS = {
    "cpf": "Pode digitar com ou sem pontos. Ex.: 529.982.247-25",
    "nome": "Nome completo, como está no documento.",
    "banco": "Código ou nome. Ex.: 001 ou Banco do Brasil",
    "agencia": "Como está no cartão: números, letras, traço e ponto. Ex.: 1234-5",
    "conta": "Número da conta com o dígito, como está escrito. Ex.: 12345-6 ou 12.345-X",
}
ROTULOS_SIMPLES = {"cpf": "CPF", "nome": "Nome", "banco": "Banco", "agencia": "Agência", "conta": "Conta"}
RESPOSTAS = {"s": Resposta.SIM, "t": Resposta.SIM_TODOS, "n": Resposta.CORRIGIR, "p": Resposta.PULAR}


def formatar_cpf(cpf: str) -> str:
    if len(cpf) == 11 and cpf.isdigit():
        return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    return cpf


def situacao_amigavel(status: str, texto: str) -> str:
    """Texto curto para a lista de resultados, sempre com símbolo e palavra."""
    motivo = texto[len(config.PREFIXO[status]):] if texto.startswith(config.PREFIXO[status]) else texto
    return {"OK": "✔ Cadastrado", "JA": "✔ Já estava cadastrado", "PULADO": "– Pulado"}.get(
        status, f"✖ Problema: {motivo}")


def mensagem_de_erro(erro: Exception) -> str:
    from automacoes.cadastro.planilha import ErroPlanilha

    if isinstance(erro, (ErroNavegador, ErroPlanilha)):
        return str(erro)
    primeira = (str(erro).splitlines() or [type(erro).__name__])[0]
    return f"Aconteceu um problema inesperado: {primeira}"


def ler_minutos(texto: str):
    """'4' -> 240; '4,5' -> 270; '4:30' -> 270. None se inválido."""
    texto = str(texto or "").strip().replace(",", ".")
    try:
        if ":" in texto:
            minutos, segundos = texto.split(":", 1)
            valor = int(minutos or 0) * 60 + int(segundos or 0)
        else:
            valor = float(texto) * 60
    except ValueError:
        return None
    return valor if valor > 0 else None


def escrever_minutos(segundos: float) -> str:
    minutos, seg = divmod(int(round(segundos)), 60)
    return f"{minutos}:{seg:02d}"


# ======================================================== o que muda na Central

geral._aplicar(geral.ano_sigef())  # SIGEF2026/... -> o ano escolhido (as trocas depois são automáticas)
config.PERFIL_CHROME = _navegador.PERFIL_CHROME = Path(PASTA_PERFIL_CHROME_AUTOMACAO)
_abrir_original = _navegador.abrir_navegador_debug


def _abrir_chrome_da_central() -> str:
    """No lugar de navegador.abrir_navegador_debug: o Chrome da Central, com as opções dela."""
    if _navegador.cdp_disponivel():
        return "navegador já aberto"
    from automacoes.sigef_sei import preparar_navegador

    try:
        preparar_navegador.achar_chrome()
    except SystemExit:
        return _abrir_original()  # sem o Chrome: o jeito do programa (procura o Edge)
    preparar_navegador.abrir_chrome_debug(config.PORTA_DEBUG, urls=[config.URL_SIGEF])
    if not _navegador.cdp_disponivel(config.ESPERA_CHROME):
        raise ErroNavegador("O Google Chrome não respondeu. Feche todas as janelas dele e tente de novo.")
    return "Google Chrome"


_navegador.abrir_navegador_debug = _abrir_chrome_da_central


# ======================================================== a linha do Chrome e do Excel


class _Trabalho:
    """A linha de execução que fala com o Chrome (Playwright) e com o Excel (COM)."""

    def __init__(self):
        self._tarefas: "queue.Queue" = queue.Queue()
        self.navegador = None
        self._linha = None
        self._trava = threading.Lock()

    def _garantir(self) -> None:
        with self._trava:
            if self._linha is None or not self._linha.is_alive():
                self._linha = threading.Thread(target=self._laco, name="cadastro-trabalho", daemon=True)
                self._linha.start()

    def fazer(self, funcao):
        """Roda `funcao()` na linha do trabalho e devolve o resultado (ou levanta o erro dela)."""
        self._garantir()
        resposta: "queue.Queue" = queue.Queue(maxsize=1)
        self._tarefas.put((funcao, resposta))
        ok, valor = resposta.get()
        if not ok:
            raise valor
        return valor

    def em_segundo_plano(self, funcao, ao_terminar) -> None:
        """Roda `funcao()` lá e chama `ao_terminar(resultado, erro)` quando acabar (na linha do trabalho)."""
        self._garantir()
        self._tarefas.put((funcao, ao_terminar))

    def encerrar(self) -> None:
        self._tarefas.put(None)

    def _laco(self) -> None:
        try:
            import pythoncom  # Excel via COM exige inicializar nesta linha de execução

            pythoncom.CoInitialize()
        except ImportError:
            pass
        playwright = None
        while True:
            tarefa = self._tarefas.get()
            if tarefa is None:
                break
            funcao, volta = tarefa
            try:
                if playwright is None:
                    from playwright.sync_api import sync_playwright

                    playwright = sync_playwright().start()
                    self.navegador = _navegador.Navegador(playwright)
                resultado, erro = funcao(), None
            except Exception as falha:  # noqa: BLE001 - nada derruba a linha do trabalho
                logger.exception("Falha em %s", getattr(funcao, "__name__", funcao))
                resultado, erro = None, falha
            if isinstance(volta, queue.Queue):
                volta.put((erro is None, erro if erro is not None else resultado))
            else:
                try:
                    volta(resultado, erro)
                except Exception:  # noqa: BLE001
                    logger.exception("Falha ao terminar")
        if playwright is not None:
            try:
                playwright.stop()  # desconecta; o navegador continua aberto
            except Exception:  # noqa: BLE001
                pass


# ======================================================== estado


class _Estado:
    def __init__(self):
        self.emitir = lambda tipo, **dados: None
        self.janela = lambda: None
        self.trabalho = _Trabalho()
        self.iniciado = False
        self.lotes: list[Lote] = []       # a lista digitada (fica ao voltar de tela)
        self.conferencia = "auto"
        self.refazer = None               # os itens com erro do último cadastro (só na memória)
        self.cadastrando = False
        self.excel = None
        self.pasta = None                 # a pasta de trabalho (Workbook) escolhida
        self.planilha = None              # a Planilha lida (aba escolhida)
        self.parar = threading.Event()
        self.respostas: "queue.Queue" = queue.Queue()
        self.esperando = None             # "conferir" | "corrigir" | None
        self.resultados: list = []        # [(linha da tabela, status)] do cadastro em andamento


_e = _Estado()


def configurar(emitir, janela) -> None:
    """Chamado uma vez pelo app_janela: como avisar a página e como achar a janela."""
    _e.emitir, _e.janela = emitir, janela


def _iniciar_uma_vez() -> None:
    if _e.iniciado:
        return
    _e.iniciado = True
    configurar_log()
    logger.info("Início da execução (Central de Automações) v%s", __version__)


def executando() -> bool:
    return _e.cadastrando


def encerrar() -> None:
    """A janela fechou: destrava uma pergunta aberta e pede para parar."""
    _e.parar.set()
    _e.respostas.put(None)
    _e.trabalho.encerrar()


def _com_o_chrome(funcao):
    """Mexe no Chrome só se nenhuma outra automação estiver usando (uma por vez)."""
    def tarefa():
        if not modulos_janela.USO_DO_CHROME.acquire(blocking=False):
            raise ErroNavegador("Outra automação está usando o Chrome agora. Espere ela terminar e tente de novo.")
        try:
            return funcao()
        finally:
            modulos_janela.USO_DO_CHROME.release()
    return tarefa


def _erro(falha: Exception) -> dict:
    return {"ok": False, "erro": mensagem_de_erro(falha), "navegador": isinstance(falha, ErroNavegador)}


def _lote_para_tela(lote: Lote) -> dict:
    return {"cpf": lote.cpf, "cpf_formatado": formatar_cpf(lote.cpf), "nome": lote.nome, "banco": lote.banco,
            "banco_nome": descrever_banco(lote.banco) if lote.banco else "", "agencia": lote.agencia,
            "conta": lote.conta}


def _lista() -> dict:
    return {"ok": True, "lotes": [_lote_para_tela(l) for l in _e.lotes]}


def _estado() -> dict:
    return {
        "ok": True, "versao": __version__, "cadastrando": _e.cadastrando, "conferencia": _e.conferencia,
        "refazer": len(_e.refazer["chaves"]) if _e.refazer else 0, "lotes": _lista()["lotes"],
        "pasta_logs": str(config.PASTA_LOGS), "ano": geral.ano_sigef(), "dicas": DICAS, "rotulos": ROTULOS_SIMPLES,
        "coluna_resultado": config.COLUNA_RESULTADO,
    }


# ======================================================== 1. entrar no SIGEF


def _abrir_navegador() -> dict:
    try:
        nome = _e.trabalho.fazer(_com_o_chrome(lambda: _e.trabalho.navegador.abrir()))
    except Exception as falha:  # noqa: BLE001
        return _erro(falha)
    aberto = "O navegador já estava aberto" if "já" in nome else f"O {nome} foi aberto"
    return {"ok": True, "texto": f"{aberto} na página do SIGEF. Entre com seu usuário e senha."}


def _conferir_login() -> dict:
    def conferir():
        navegador = _e.trabalho.navegador
        navegador.abrir()
        return navegador.logado()

    try:
        logado = _e.trabalho.fazer(_com_o_chrome(conferir))
    except Exception as falha:  # noqa: BLE001
        return _erro(falha)
    return {"ok": True, "logado": bool(logado)}


# ======================================================== 2. os dados: digitar ou colar


def _validar_pessoa(valores: dict) -> dict:
    """Formulario.ler() da janela original: o Lote limpo ou os campos com problema."""
    lote, erros, avisos = Lote(), {}, {}
    for campo in ROTULOS:
        bruto = str((valores or {}).get(campo) or "")
        valor = limpar(campo, bruto)
        setattr(lote, campo, valor)
        if not valor:
            erros[campo] = ("Banco não reconhecido. Digite o código (ex.: 001)." if campo == "banco" and bruto.strip()
                            else "Preencha este campo.")
        elif campo == "cpf" and len(valor) != 11:
            erros[campo] = "O CPF precisa ter 11 números."
    if lote.banco:
        avisos["banco"] = f"✔ {descrever_banco(lote.banco)}"
    return {"ok": not erros, "erros": erros, "avisos": avisos, "lote": _lote_para_tela(lote),
            "cpf_suspeito": bool(lote.cpf and len(lote.cpf) == 11 and not cpf_confere(lote.cpf)), "_lote": lote}


def _banco(texto: str) -> dict:
    """A dica do campo Banco enquanto se digita."""
    if not str(texto or "").strip():
        return {"ok": True, "texto": "", "problema": False}
    codigo = limpar("banco", texto)
    if codigo:
        return {"ok": True, "texto": f"✔ {descrever_banco(codigo)}", "problema": False}
    return {"ok": True, "texto": "Banco não reconhecido. Digite o código (ex.: 001).", "problema": True}


def _sem_objeto(resposta: dict) -> dict:
    return {chave: valor for chave, valor in resposta.items() if not chave.startswith("_")}


def _adicionar(valores: dict, forcar: bool) -> dict:
    validado = _validar_pessoa(valores)
    if not validado["ok"]:
        return _sem_objeto(validado)
    if validado["cpf_suspeito"] and not forcar:
        return {**_sem_objeto(validado), "ok": False, "confirmar_cpf": True}
    _e.lotes.append(validado["_lote"])
    return _lista()


def _remover(indice) -> dict:
    try:
        del _e.lotes[int(indice)]
    except (TypeError, ValueError, IndexError):
        return {"ok": False, "erro": "Primeiro clique na pessoa que você quer tirar da lista."}
    return _lista()


def _ignoradas(ignoradas) -> list:
    return [{"linha": n, "motivo": motivo} for n, motivo in ignoradas]


def _colar(texto: str, forcar: bool) -> dict:
    lotes, ignoradas = lotes_de_texto(texto or "")
    if ignoradas and not forcar:
        return {"ok": False, "ignoradas": _ignoradas(ignoradas), "validas": len(lotes)}
    _e.lotes.extend(lotes)
    return {**_lista(), "adicionadas": len(lotes)}


def _abrir_lista() -> dict:
    import webview

    escolhido = _e.janela().create_file_dialog(
        webview.FileDialog.OPEN, file_types=("Arquivos de texto ou CSV (*.csv;*.txt)", "Todos os arquivos (*.*)"))
    if not escolhido:
        return {"ok": False, "cancelou": True}
    try:
        lotes, ignoradas = ler_arquivo_lotes(escolhido[0])
    except OSError as erro:
        return {"ok": False, "erro": f"Não consegui abrir o arquivo: {erro}"}
    _e.lotes.extend(lotes)
    return {**_lista(), "adicionadas": len(lotes), "ignoradas": _ignoradas(ignoradas)}


# ======================================================== 2. os dados: planilha do Excel


def _planilhas_abertas() -> dict:
    from automacoes.cadastro.planilha import conectar_excel, pastas_abertas

    def buscar():
        _e.excel = _e.excel or conectar_excel()
        return pastas_abertas(_e.excel)

    try:
        return {"ok": True, "pastas": list(_e.trabalho.fazer(buscar))}
    except Exception as falha:  # noqa: BLE001
        return _erro(falha)


def _procurar_planilha() -> dict:
    import webview

    from automacoes.cadastro.planilha import abrir_arquivo, conectar_excel

    escolhido = _e.janela().create_file_dialog(
        webview.FileDialog.OPEN, file_types=("Planilhas do Excel (*.xlsx;*.xlsm;*.xls)", "Todos os arquivos (*.*)"))
    if not escolhido:
        return {"ok": False, "cancelou": True}
    caminho = escolhido[0].replace("/", "\\")

    def abrir():
        _e.excel = _e.excel or conectar_excel()
        pasta, _ = abrir_arquivo(_e.excel, caminho)
        return pasta.Name

    try:
        nome = _e.trabalho.fazer(abrir)
    except Exception as falha:  # noqa: BLE001
        return _erro(falha)
    return {**_planilhas_abertas(), "selecionar": nome}


def _abas(indice) -> dict:
    from automacoes.cadastro.planilha import abas_da_pasta

    def ler():
        _e.pasta = _e.excel.Workbooks(int(indice) + 1)
        return abas_da_pasta(_e.pasta)

    try:
        return {"ok": True, "abas": list(_e.trabalho.fazer(ler))}
    except Exception as falha:  # noqa: BLE001
        return _erro(falha)


def _amostra_para_tela(amostra) -> list:
    return [{"campo": campo, "rotulo": ROTULOS_SIMPLES[campo], "letra": letra, "titulo": titulo or "",
             "exemplo": exemplo or ""} for campo, letra, titulo, exemplo in amostra]


def _ler_planilha(aba: str) -> dict:
    from automacoes.cadastro.planilha import Planilha, indice_para_letra

    def ler():
        planilha = Planilha.da_pasta(_e.pasta, aba)
        colunas, primeira, detectou = planilha.colunas_sugeridas()
        _e.planilha = planilha
        return {
            "ok": True,
            "colunas": {campo: indice_para_letra(indice) for campo, indice in colunas.items()},
            "primeira": primeira,
            "detectou": detectou,
            "final": max(planilha.ultima_linha(colunas), primeira),
            "amostra": _amostra_para_tela(planilha.amostra(colunas, primeira)),
            "nome": f"{_e.pasta.Name} › {aba}",
            "somente_leitura": bool(planilha.somente_leitura),
            "letras": [indice_para_letra(i) for i in range(1, 53)],  # A até AZ
        }

    try:
        return _e.trabalho.fazer(ler)
    except Exception as falha:  # noqa: BLE001
        return _erro(falha)


def _colunas_da_tela(letras: dict) -> dict:
    from automacoes.cadastro.planilha import letra_para_indice

    return {campo: letra_para_indice(str(letras.get(campo) or "")) for campo in ROTULOS}


def _amostra(letras: dict, primeira) -> dict:
    if _e.planilha is None:
        return {"ok": False, "erro": "Escolha a planilha de novo."}
    colunas = _colunas_da_tela(letras)
    try:
        amostra = _e.trabalho.fazer(lambda: _e.planilha.amostra(colunas, int(primeira)))
    except Exception as falha:  # noqa: BLE001
        return _erro(falha)
    return {"ok": True, "amostra": _amostra_para_tela(amostra)}


def problema_das_colunas(colunas: dict, primeira, final, resultado: int) -> str:
    """TelaColunas.validar() da janela original ('' = tudo certo)."""
    if not primeira or not final:
        return "Informe os números da primeira e da última linha."
    if primeira > final:
        return "A linha de começo precisa ser menor que a linha do fim."
    if resultado in colunas.values():
        return "A coluna do resultado não pode ser uma das colunas com os dados. Escolha uma coluna vazia."
    return ""


# ======================================================== 3. cadastrar


class _RelatorJanela(Relator):
    """Leva o andamento para a página; a correção e a conferência viram perguntas na tela."""

    def inicio(self, chave, lote, atual, total):
        _e.emitir("cad_inicio", chave=chave, atual=atual, total=total, lote=_lote_para_tela(lote))

    def resultado(self, chave, lote, status, texto):
        linha = [chave, lote.nome, formatar_cpf(lote.cpf), situacao_amigavel(status, texto)]
        _e.resultados = [r for r in _e.resultados if r[0][0] != chave] + [(linha, status)]
        _e.emitir("cad_resultado", chave=chave, status=status, linha=linha)

    def aviso(self, texto):
        _e.emitir("cad_aviso", texto=texto)

    def corrigir(self, lote):
        resposta = _perguntar_na_tela("corrigir", lote=_lote_para_tela(lote))
        if not isinstance(resposta, Lote):
            return False
        for campo in ROTULOS:
            setattr(lote, campo, getattr(resposta, campo))
        return True

    def cancelado(self):
        return _e.parar.is_set()


def _perguntar_na_tela(tipo: str, **dados):
    """Mostra a pergunta na página e espera a resposta (chega por responder/corrigido)."""
    while not _e.respostas.empty():  # resposta velha (clique duplo) não vale para esta pergunta
        _e.respostas.get_nowait()
    _e.esperando = tipo
    _e.emitir(f"cad_{tipo}", **dados)
    try:
        return _e.respostas.get()
    finally:
        _e.esperando = None
        _e.emitir("cad_pergunta_fim")


def _conferir(lote: Lote, acao: str, editavel: bool) -> Resposta:
    """O 'Confira antes de gravar' da janela original. Fechar = pular: nada é gravado sem um sim."""
    valor = _perguntar_na_tela("conferir", pergunta=PERGUNTAS.get(acao, acao), lote=_lote_para_tela(lote),
                               editavel=bool(editavel))
    resposta = RESPOSTAS.get(valor, Resposta.PULAR)
    if resposta is Resposta.CORRIGIR and not editavel:
        return Resposta.PULAR
    return resposta


def _comecar(d: dict) -> dict:
    if _e.cadastrando:
        return {"ok": False, "erro": "O cadastro já está acontecendo."}
    refazendo = bool(d.get("refazer"))
    if refazendo:
        if not _e.refazer:
            return {"ok": False, "erro": "Não há pessoas com erro para refazer."}
        p = {chave: valor for chave, valor in _e.refazer.items() if chave != "chaves"}
        modo, manual = p.pop("modo"), p.pop("manual")
    else:
        modo = d.get("modo")
        manual = bool(d.get("manual"))
        _e.conferencia = "manual" if manual else "auto"
        if modo == "planilha":
            from automacoes.cadastro.planilha import letra_para_indice

            if _e.planilha is None:
                return {"ok": False, "erro": "Escolha a planilha de novo."}
            colunas = _colunas_da_tela(d.get("colunas") or {})
            try:
                primeira, final = int(d.get("primeira")), int(d.get("final"))
            except (TypeError, ValueError):
                primeira = final = None
            resultado = str(d.get("coluna_resultado") or config.COLUNA_RESULTADO)
            problema = problema_das_colunas(colunas, primeira, final, letra_para_indice(resultado))
            if problema:
                return {"ok": False, "erro": problema}
            p = {"planilha": _e.planilha, "colunas": colunas, "linhas": range(primeira, final + 1),
                 "coluna_resultado": resultado}
        elif modo == "lotes":
            if not _e.lotes:
                return {"ok": False, "erro": "A lista está vazia."}
            p = {"lotes": list(_e.lotes)}
        else:
            return {"ok": False, "erro": f"modo desconhecido: {modo}"}

    if not modulos_janela.USO_DO_CHROME.acquire(blocking=False):
        return {"ok": False, "erro": "Outra automação está usando o Chrome agora. Espere ela terminar e tente de novo."}

    _e.cadastrando = True
    _e.parar.clear()
    _e.resultados = []
    while not _e.respostas.empty():
        _e.respostas.get_nowait()
    sessao = estatisticas.Sessao(modo, "manual" if manual else "auto")
    perguntar = _conferir if manual else None
    relator = _RelatorJanela()

    def tarefa():
        navegador = _e.trabalho.navegador
        try:
            if modo == "planilha":
                return executar_planilha(navegador, p["planilha"], p["colunas"], p["linhas"], p["coluna_resultado"],
                                         relator, perguntar, sessao)
            return executar_lotes(navegador, p["lotes"], relator, perguntar, sessao, p.get("numeros"))
        finally:
            estatisticas.salvar_sessao(sessao)  # aqui, para a rede lenta não travar a janela

    def terminou(resumo, erro):
        try:
            _terminou(resumo, erro, modo, manual, p, sessao)
        finally:
            _e.cadastrando = False
            modulos_janela.USO_DO_CHROME.release()

    _e.trabalho.em_segundo_plano(tarefa, terminou)
    return {"ok": True, "modo": modo, "manual": manual, "refazendo": refazendo,
            "chave": "Linha" if modo == "planilha" else "Nº"}


def _guardar_erros(resumo, modo, manual, p) -> None:
    """Guarda na memória (só enquanto a Central estiver aberta) o que deu erro, para refazer."""
    if not resumo.falhas:
        _e.refazer = None
        return
    chaves = [chave for chave, _lote in resumo.falhas]
    dados = {"modo": modo, "manual": manual, "chaves": chaves}
    if modo == "planilha":
        # Só as linhas: elas são lidas de novo, já com o que for corrigido na planilha.
        dados.update(planilha=p["planilha"], colunas=p["colunas"], coluna_resultado=p["coluna_resultado"],
                     linhas=chaves)
    else:
        dados.update(lotes=[lote for _chave, lote in resumo.falhas], numeros=chaves)
    _e.refazer = dados


def _terminou(resumo, erro, modo, manual, p, sessao) -> None:
    parado = _e.parar.is_set()
    interrompido = parado or erro is not None
    if erro is None and modo == "lotes":
        _e.lotes.clear()  # a lista digitada foi feita (como no programa original)
    if erro is None and not parado:  # parado no meio, a memória fica como estava
        _guardar_erros(resumo, modo, manual, p)

    contagem = dict.fromkeys(config.PREFIXO, 0)
    for _linha, status in _e.resultados:
        contagem[status] += 1
    if resumo is not None:
        contagem = dict(resumo.contagem)

    economia = ""
    if contagem["OK"]:
        _, automacao, ganho = estatisticas.resumo_da_sessao(sessao)
        economia = (f"A automação levou {estatisticas.formatar_duracao(automacao)}. Feito à mão, levaria cerca de "
                    f"{estatisticas.formatar_duracao(automacao + ganho)}: uma economia de "
                    f"{estatisticas.formatar_duracao(ganho)}. Veja o total em Estatísticas.")
    _e.emitir(
        "cad_fim", modo=modo, manual=manual, interrompido=interrompido, contagem=contagem, economia=economia,
        resultados=[{"linha": linha, "status": status} for linha, status in _e.resultados],
        erro=mensagem_de_erro(erro) if erro is not None else "", navegador=isinstance(erro, ErroNavegador),
        refazer=len(_e.refazer["chaves"]) if (_e.refazer and erro is None and not parado) else 0,
        processados=sum(contagem.values()),
    )


def _responder(valor) -> dict:
    if _e.esperando != "conferir":
        return {"ok": False}
    _e.respostas.put(str(valor or "p"))
    return {"ok": True}


def _corrigido(d: dict) -> dict:
    if _e.esperando != "corrigir":
        return {"ok": False}
    if d.get("pular"):
        _e.respostas.put(None)
        return {"ok": True}
    validado = _validar_pessoa(d.get("valores") or {})
    if not validado["ok"]:
        return _sem_objeto(validado)
    _e.respostas.put(validado["_lote"])
    return {"ok": True}


def _parar() -> dict:
    """Termina a pessoa atual e para. Com uma pergunta aberta, ela vale como "pular" (nada é gravado)."""
    _e.parar.set()
    if _e.esperando == "conferir":
        _e.respostas.put("p")
    elif _e.esperando == "corrigir":
        _e.respostas.put(None)
    return {"ok": True}


# ======================================================== estatísticas


def _fmt(segundos) -> str:
    return estatisticas.formatar_duracao(segundos, curto=True)


def _estatisticas(escopo: str = None) -> dict:
    ajustes = estatisticas.ler_ajustes()
    escopo = escopo or (estatisticas.TODOS if ajustes["pasta_pesquisa"] else estatisticas.LOCAL)
    try:
        sessoes, manuais = estatisticas.carregar(escopo)
        ind = estatisticas.calcular(sessoes, manuais, ajustes["estimativa"])
    except Exception as falha:  # noqa: BLE001
        return _erro(falha)
    linhas = []
    for sessao in reversed(sessoes[-200:]):
        itens = sessao.get("itens", [])
        manual, automacao = estatisticas.economia_de(itens, ind.media_manual)
        feitos = sum(i.get("status") == "OK" for i in itens)
        erros = sum(i.get("status") == "ERRO" for i in itens)
        linhas.append({"data": estatisticas.formatar_data(sessao.get("inicio", "")),
                       "computador": sessao.get("computador", ""), "pessoas": len(itens), "feitos": feitos,
                       "erros": erros, "automacao": _fmt(automacao),
                       "economia": _fmt(manual - automacao) if feitos else "-",
                       "tom": "OK" if feitos and not erros else ("ERRO" if erros else "")})
    estimados = [estatisticas.ROTULO_CAMINHO[c].lower() for c in ind.amostras_manuais if not ind.amostras_manuais[c]]
    return {
        "ok": True, "escopo": escopo, "pasta_pesquisa": ajustes["pasta_pesquisa"],
        "situacao": (f"{ind.sessoes} sessões · {ind.computadores} computador(es)" if ind.sessoes
                     else "Ainda não há sessões registradas."),
        "feitos": ind.feitos,
        "economizado": _fmt(ind.segundos_economizados) if ind.feitos else "-",
        "media_manual": _fmt(ind.media_manual_geral), "media_manual_s": ind.media_manual_geral,
        "media_automacao": _fmt(ind.media_automacao) if ind.feitos else "-",
        "media_automacao_s": ind.media_automacao if ind.feitos else 0,
        "detalhe": (f"{estatisticas.formatar_vezes(ind.vezes_mais_rapido)} mais rápido  ·  {ind.contagem['JA']} já "
                    f"tinham cadastro  ·  {ind.contagem['ERRO']} com erro  ·  {ind.taxa_sucesso:.0%} de sucesso"
                    if ind.feitos else "Faça um cadastro com a automação para ver a comparação."),
        "aviso_manual": ("O tempo à mão ainda é uma estimativa para: " + "; ".join(estimados) +
                         ". Cronometre alguns cadastros feitos à mão para ter o valor real." if estimados else ""),
        "sessoes": linhas,
        "estimativa": {chave: escrever_minutos(valor) for chave, valor in ajustes["estimativa"].items()},
    }


def _salvar_tempo_manual(caminho: str, segundos) -> dict:
    try:
        segundos = float(segundos)
    except (TypeError, ValueError):
        return {"ok": False, "erro": "Tempo inválido."}
    if caminho not in (estatisticas.NOVO, estatisticas.EXISTENTE):
        return {"ok": False, "erro": "Escolha o tipo de cadastro."}
    try:
        estatisticas.salvar_tempo_manual(caminho, segundos)
    except Exception as falha:  # noqa: BLE001
        return _erro(falha)
    return {"ok": True, "texto": f"Cadastro manual de {estatisticas.formatar_duracao(segundos)} guardado para a "
                                 "pesquisa. Obrigado!"}


def _salvar_estimativa(valores: dict) -> dict:
    novo, erros = {}, {}
    for chave in (estatisticas.NOVO, estatisticas.EXISTENTE):
        valor = ler_minutos((valores or {}).get(chave))
        if valor is None:
            erros[chave] = "Digite os minutos. Exemplo: 5 ou 4:30"
        else:
            novo[chave] = valor
    if erros:
        return {"ok": False, "erros": erros}
    ajustes = estatisticas.ler_ajustes()
    ajustes["estimativa"] = novo
    estatisticas.gravar_ajustes(ajustes)
    return {"ok": True}


def _pasta_pesquisa(acao: str) -> dict:
    ajustes = estatisticas.ler_ajustes()
    if acao == "parar":
        ajustes["pasta_pesquisa"] = ""
        estatisticas.gravar_ajustes(ajustes)
        return {"ok": True, "pasta": ""}
    import webview

    escolhida = _e.janela().create_file_dialog(webview.FileDialog.FOLDER)
    if not escolhida:
        return {"ok": False, "cancelou": True}
    pasta = escolhida[0] if isinstance(escolhida, (list, tuple)) else escolhida
    ajustes["pasta_pesquisa"] = os.path.normpath(pasta)
    estatisticas.gravar_ajustes(ajustes)
    copiou = estatisticas.sincronizar()
    aviso = ("Não consegui gravar na pasta. Confira se você tem permissão para gravar nessa pasta da rede."
             if not copiou and estatisticas.arquivo_local().exists() else "")
    return {"ok": True, "pasta": ajustes["pasta_pesquisa"], "aviso": aviso}


def _importar() -> dict:
    import webview

    arquivos = _e.janela().create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True,
                                              file_types=("Dados da pesquisa (*.jsonl)", "Todos os arquivos (*.*)"))
    if not arquivos:
        return {"ok": False, "cancelou": True}
    try:
        total = estatisticas.importar_arquivos(list(arquivos))
    except Exception as falha:  # noqa: BLE001
        return _erro(falha)
    return {"ok": True, "texto": f"{total} arquivo(s) de outros computadores foram juntados. Eles aparecem em "
                                 "Todos os computadores."}


def _abrir_pasta(caminho) -> dict:
    caminho = Path(caminho)
    caminho.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(caminho)  # noqa: S606 - pasta do próprio programa
    return {"ok": True}


def _relatorio(escopo: str) -> dict:
    try:
        pasta = relatorio.gerar(escopo or estatisticas.LOCAL)
    except Exception as falha:  # noqa: BLE001
        logger.exception("Falha no relatório")
        return _erro(falha)
    _abrir_pasta(pasta)
    return {"ok": True, "pasta": str(pasta)}


# ======================================================== porta

_ACOES = {
    "estado": lambda d: _estado(),
    "abrir_navegador": lambda d: _abrir_navegador(),
    "conferir_login": lambda d: _conferir_login(),
    "banco": lambda d: _banco(d.get("texto", "")),
    "validar": lambda d: _sem_objeto(_validar_pessoa(d.get("valores") or {})),
    "adicionar": lambda d: _adicionar(d.get("valores") or {}, bool(d.get("forcar"))),
    "remover": lambda d: _remover(d.get("indice")),
    "colar": lambda d: _colar(d.get("texto", ""), bool(d.get("forcar"))),
    "abrir_lista": lambda d: _abrir_lista(),
    "lista": lambda d: _lista(),
    "planilhas": lambda d: _planilhas_abertas(),
    "procurar_planilha": lambda d: _procurar_planilha(),
    "abas": lambda d: _abas(d.get("indice", 0)),
    "ler_planilha": lambda d: _ler_planilha(d.get("aba", "")),
    "amostra": lambda d: _amostra(d.get("colunas") or {}, d.get("primeira") or 1),
    "comecar": _comecar,
    "responder": lambda d: _responder(d.get("valor")),
    "corrigido": _corrigido,
    "parar": lambda d: _parar(),
    "estatisticas": lambda d: _estatisticas(d.get("escopo")),
    "tempo_manual": lambda d: _salvar_tempo_manual(d.get("caminho", ""), d.get("segundos")),
    "estimativa": lambda d: _salvar_estimativa(d.get("valores") or {}),
    "pasta_pesquisa": lambda d: _pasta_pesquisa(d.get("acao", "")),
    "importar": lambda d: _importar(),
    "abrir_dados": lambda d: _abrir_pasta(estatisticas.PASTA_ESTATISTICAS),
    "abrir_registros": lambda d: _abrir_pasta(config.PASTA_LOGS),
    "relatorio": lambda d: _relatorio(d.get("escopo", "")),
}


def chamar(acao: str, dados: dict | None = None) -> dict:
    """A porta única da página do Cadastro: chamar("adicionar", {...}) etc."""
    funcao = _ACOES.get(acao)
    if funcao is None:
        return {"ok": False, "erro": f"ação desconhecida: {acao}"}
    _iniciar_uma_vez()
    try:
        return funcao(dados or {})
    except Exception as falha:  # noqa: BLE001 - a página sempre recebe uma resposta
        logger.exception("Falha em %s", acao)
        print(traceback.format_exc())
        return _erro(falha)
