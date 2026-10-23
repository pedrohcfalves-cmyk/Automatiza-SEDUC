"""
A automação SIGEF -> SEI numa janela, no lugar da tela preta.

    python app_janela.py        (ou o atalho do programa instalado)

Faz o mesmo que o main.py, na mesma ordem, e usa as mesmas funções das
etapas em automacoes/sigef_sei/. O que muda é só a conversa com o usuário: botões
e campos em vez de print() e input(). A interface é uma página HTML
(pasta janela/interface/) aberta numa janela própria pelo pywebview.

COMO AS DUAS PONTAS CONVERSAM

    janela (JS) ──comando──▶ fila ──▶ trabalhador (thread)  ──▶ SIGEF/SEI
    janela (JS) ◀──evento── fila ◀── print() / input() / avisos

Tudo que toca o Playwright roda numa thread só, o "trabalhador": a API
síncrona do Playwright não aceita ser usada de threads diferentes. Os
botões da janela só põem um comando na fila dele.

Os módulos de automação continuam falando por print() e input(). Aqui o
print vira linha no registro da janela, e o input vira uma pergunta na
tela -- assim nenhum deles precisou mudar para funcionar nos dois modos.
"""
import builtins
import json
import os
import queue
import sys
import threading
import time
import traceback


# ---------------------------------------------------------------- Pastas

# Onde estão index.html, css e js: dentro do pacote, quando instalado.
PASTA_PROGRAMA = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
PASTA_INTERFACE = os.path.join(PASTA_PROGRAMA, "janela", "interface")

# Os documentos baixados e a sessão vão para Documentos\Automacao
# SIGEF-SEI: quem decide é o PASTA_BASE do etapa_listar_baixar.


# ----------------------------------------------- Ponte com a janela (JS)


class Ponte:
    """
    Leva eventos do Python para a janela.

    Os eventos são acumulados e mandados em lote a cada fração de
    segundo: o download imprime dezenas de linhas seguidas, e uma
    chamada ao JS por linha travaria a janela.
    """

    def __init__(self):
        self.janela = None
        self._fila = queue.Queue()
        threading.Thread(target=self._bombear, daemon=True).start()

    def emitir(self, tipo: str, **dados) -> None:
        self._fila.put({"tipo": tipo, **dados})

    def _bombear(self) -> None:
        while True:
            lote = [self._fila.get()]
            time.sleep(0.12)
            while not self._fila.empty():
                lote.append(self._fila.get_nowait())
            if self.janela is None:
                continue
            try:
                self.janela.run_js(f"window.lba && lba.receber({json.dumps(lote)})")
            except Exception:
                pass


ponte = Ponte()


# Arquivo onde o registro também é gravado (ver gravar_registro_em): o
# registro da janela some ao fechar, e sem ele não dá pra saber onde um
# erro aconteceu.
_arquivo_registro = None


def gravar_registro_em(pasta: str) -> None:
    """Passa a gravar o registro em <pasta>/registros/registro_AAAA-MM-DD.txt."""
    global _arquivo_registro
    try:
        pasta_registros = os.path.join(pasta, "registros")
        os.makedirs(pasta_registros, exist_ok=True)
        caminho = os.path.join(pasta_registros, time.strftime("registro_%Y-%m-%d.txt"))
        _arquivo_registro = open(caminho, "a", encoding="utf-8", buffering=1)
        _arquivo_registro.write(f"\n===== {time.strftime('%d/%m/%Y %H:%M:%S')} programa aberto =====\n")
    except OSError:
        _arquivo_registro = None


class SaidaParaJanela:
    """Troca o sys.stdout: cada linha impressa vira uma linha do registro."""

    encoding = "utf-8"

    def __init__(self, original):
        self._original = original
        self._pedaco = ""
        self._trava = threading.Lock()

    def write(self, texto) -> int:
        texto = str(texto)
        if self._original is not None:
            try:
                self._original.write(texto)
            except Exception:
                pass
        with self._trava:
            self._pedaco += texto
            *linhas, self._pedaco = self._pedaco.split("\n")
        for linha in linhas:
            ponte.emitir("log", texto=linha)
            if _arquivo_registro is not None:
                try:
                    _arquivo_registro.write(f"{time.strftime('%H:%M:%S')} {linha}\n")
                except Exception:
                    pass
        return len(texto)

    def flush(self) -> None:
        if self._original is not None:
            try:
                self._original.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        return False


sys.stdout = SaidaParaJanela(sys.stdout)
sys.stderr = SaidaParaJanela(sys.stderr)


# Só depois de trocar a saída: os módulos imprimem já no import.
from automacoes.sigef_sei.etapa_listar_baixar import (  # noqa: E402
    PASTA_BASE,
    baixar_documentos,
    carregar_sessao,
    normalizar_processo_sei,
    salvar_sessao,
)
from automacoes.sigef_sei import etapa_sei2  # noqa: E402
from automacoes.sigef_sei.documentos import DOCUMENTOS, normalizar_documentos  # noqa: E402
from automacoes.sigef_sei import metricas  # noqa: E402
from automacoes.sigef_sei import relatorio_gerencial  # noqa: E402
from janela import modulos_janela  # noqa: E402
from janela import licenca  # noqa: E402
from janela import cache_janela  # noqa: E402
from datetime import date  # noqa: E402

# Preferências que valem entre uma abertura e outra (ex.: o tempo manual
# por OB usado no relatório gerencial).
CAMINHO_CONFIG = os.path.join(PASTA_BASE, "config.json")


def _ler_config() -> dict:
    try:
        with open(CAMINHO_CONFIG, encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except (OSError, ValueError):
        return {}


def _gravar_config(**valores) -> None:
    config = _ler_config()
    config.update(valores)
    try:
        with open(CAMINHO_CONFIG, "w", encoding="utf-8") as arquivo:
            json.dump(config, arquivo, ensure_ascii=False, indent=2)
    except OSError:
        pass

gravar_registro_em(PASTA_BASE)
from automacoes.sigef_sei import lote  # noqa: E402
from main import VERSAO  # noqa: E402
from automacoes.sigef_sei.preparar_navegador import (  # noqa: E402
    DOMINIO_BB,
    DOMINIO_SEI,
    DOMINIO_SIGEF,
    URL_BB_LOGIN,
    URL_SEI,
    URL_SIGEF_LISTAR_OB,
    URL_SIGEF_PORTAL,
    _garantir_url_certa,
    abrir_ou_reusar_aba,
    conectar_chrome,
)

# Os dois tipos de documento da OB no SEI. A janela fala em chaves curtas;
# as etapas e a sessão guardam o texto do link (TEXTO_LINK_OB_*).
TIPOS_OB = {
    "regularizacao": etapa_sei2.TEXTO_LINK_OB_REGULARIZACAO,
    "ordem_bancaria": etapa_sei2.TEXTO_LINK_OB_NORMAL,
}


def _chave_do_tipo(texto: str) -> str:
    return next((chave for chave, nome in TIPOS_OB.items() if nome == texto), "regularizacao")


# --------------------------------------------- input() vira pergunta na tela


class Encerrado(Exception):
    """A janela foi fechada enquanto a automação esperava uma resposta."""

    interromper_lote = True  # não é "erro deste processo": para o lote todo


_respostas = queue.Queue()
_modo_pergunta = {"valor": "texto"}


def entrada_pela_janela(pergunta: str = "") -> str:
    """
    Substitui o input(). Mostra a pergunta na janela e espera a resposta.

    Hoje o único input() que sobra dentro das etapas é o do fim do SEI
    (conferir e apertar ENTER), que a janela mostra como a tela de
    conferência. Qualquer outro que apareça no futuro cai numa caixa de
    pergunta genérica, em vez de travar o programa sem ninguém ver.
    """
    ponte.emitir("pergunta", texto=str(pergunta).strip(), modo=_modo_pergunta["valor"])
    resposta = _respostas.get()
    _modo_pergunta["valor"] = "texto"
    if resposta is None:
        raise Encerrado()
    return resposta


builtins.input = entrada_pela_janela


# Cronômetro da OB avulsa em andamento (o lote cuida do seu em lote.py).
_cron_atual = {"valor": None}


def _aviso_conferencia(processo: str = "", avisos=()) -> None:
    """No lugar do aviso impresso: o próximo input() é a tela de conferência."""
    # A automação terminou aqui: o tempo de conferir não entra na métrica.
    if _cron_atual["valor"] is not None:
        _cron_atual["valor"].parar()
    _modo_pergunta["valor"] = "conferencia"
    ponte.emitir("avisos", avisos=list(avisos))


etapa_sei2.aviso_conferencia_final = _aviso_conferencia


# ----------------------------------------------------------- Trabalhador


def _mensagem_de(erro: BaseException) -> str:
    texto = str(erro.code if isinstance(erro, SystemExit) else erro).strip()
    return texto or "A automação parou sem dar detalhes."


class Trabalhador(threading.Thread):
    """
    A única thread que fala com o Chrome. Espera comandos da janela e
    executa um de cada vez:

        conectar          abre o Chrome da automação e as duas abas
        apos_login        leva a aba do SIGEF do portal para a tela da OB
        processar         baixa uma OB no SIGEF e anexa no SEI
        lote              faz o mesmo para uma lista de OBs (lote.py)
        sair              solta a conexão e termina
    """

    def __init__(self):
        super().__init__(daemon=True)
        self.comandos = queue.Queue()
        self.playwright = None
        self.browser = None
        self.context = None
        self.aba_sigef = None
        # Pedido de "parar o lote", lido entre um processo e outro.
        self.parar_lote = threading.Event()

    def run(self) -> None:
        while True:
            comando, argumentos = self.comandos.get()
            if comando == "sair":
                break
            # Baixar/anexar mexe no Chrome: não roda junto com o BB nem com o DARE.
            usa_chrome = comando in ("processar", "lote")
            if usa_chrome and not modulos_janela.USO_DO_CHROME.acquire(blocking=False):
                ponte.emitir(
                    "erro", fase=comando,
                    mensagem="Outra automação (BB ou DARE) está usando o Chrome agora. "
                             "Espere ela terminar e clique em “Continuar de onde parou”.",
                )
                continue
            try:
                getattr(self, f"_{comando}")(**argumentos)
            except Encerrado:
                break
            except BaseException as erro:  # SystemExit é o jeito das etapas pararem
                if not isinstance(erro, SystemExit):
                    print(traceback.format_exc())
                ponte.emitir("erro", fase=comando, mensagem=_mensagem_de(erro))
            finally:
                if usa_chrome:
                    modulos_janela.USO_DO_CHROME.release()
        self._soltar()

    # ---- comandos ----

    def _conectar(self) -> None:
        ponte.emitir("conectando")
        if self.browser is None or not self.browser.is_connected():
            self._soltar()
            self.playwright, self.browser, self.context = conectar_chrome()

        print("Conferindo as abas dos sistemas:")
        # O SIGEF abre no PORTAL: entrar direto na tela da OB sem sessão
        # dá o alerta de "sessão expirada" (ver automacoes/sigef_sei/preparar_navegador.py).
        self.aba_sigef = abrir_ou_reusar_aba(self.context, DOMINIO_SIGEF, URL_SIGEF_PORTAL, "SIGEF")
        abrir_ou_reusar_aba(self.context, DOMINIO_SEI, URL_SEI, "SEI")
        # O portal do BB (módulo Banco do Brasil) abre junto, já na entrada
        # com chave J. Se o BB estiver fora do ar, só avisa: SIGEF e SEI
        # seguem normalmente.
        try:
            abrir_ou_reusar_aba(self.context, DOMINIO_BB, URL_BB_LOGIN, "Banco do Brasil")
        except Exception as erro:
            print(f"   ⚠️  Não consegui abrir o portal do BB agora ({erro}) -- abra depois, se for usar o módulo BB.")
        try:
            self.aba_sigef.bring_to_front()
        except Exception:
            pass
        ponte.emitir("conectado")

    def _apos_login(self) -> None:
        """O usuário confirmou o login: a aba do SIGEF sai do portal para a tela da OB."""
        print("🔁 Redirecionando a aba do SIGEF para a tela de Ordem Bancária...")
        try:
            self.aba_sigef.goto(URL_SIGEF_LISTAR_OB, timeout=60000)
        except Exception:
            pass  # baixar_documentos confere a sessão de novo antes de usar
        _garantir_url_certa(self.aba_sigef, DOMINIO_SIGEF, URL_SIGEF_LISTAR_OB, "SIGEF")

    def _garantir_conexao(self) -> None:
        # O Chrome pode ter sido fechado entre uma OB e outra: reconecta
        # sozinho. O login fica no perfil, então costuma continuar valendo.
        if self.browser is None or not self.browser.is_connected():
            print("O navegador da automação tinha sido fechado -- abrindo de novo.")
            self._conectar()

    def _processar(self, processo: str, ob: str, tipo_ob: str, documentos=None) -> None:
        self._garantir_conexao()

        salvar_sessao(processo=processo, ob=ob, tipo_ob=tipo_ob)

        cron = metricas.Cronometro("avulsa", processo, ob, tipo_ob)
        _cron_atual["valor"] = cron
        dados = None
        try:
            cron.etapa("sigef")
            ponte.emitir("etapa", etapa="sigef")
            dados = baixar_documentos(self.context, self.aba_sigef, processo, ob, documentos=documentos)
            ponte.emitir("resumo", resumo=_resumo(dados))

            cron.etapa("sei")
            ponte.emitir("etapa", etapa="sei")
            etapa_sei2.executar_sei2(
                self.context, processo, dados=dados, tipo_ob=tipo_ob, documentos=documentos
            )
        except Encerrado:
            cron.registrar("parado", dados=dados, mensagem="Janela fechada")
            raise
        except BaseException as erro:
            cron.registrar("erro", dados=dados, mensagem=_mensagem_de(erro))
            raise
        finally:
            _cron_atual["valor"] = None

        tempos = cron.registrar("ok", dados=dados)
        ponte.emitir("concluido", processo=processo, ob=dados.get("ob", ob), tempos=tempos)

    def _lote(self, itens: list, documentos=None) -> None:
        self._garantir_conexao()
        self.parar_lote.clear()
        validos = [item for item in itens if item.valido]
        ponte.emitir("lote_inicio", itens=[_item_para_tela(item) for item in validos])

        def ao_mudar(indice, resultado):
            ponte.emitir(
                "lote_item", indice=indice, estado=resultado.estado,
                mensagem=resultado.mensagem, avisos=resultado.avisos, pasta=resultado.pasta,
                tempo=resultado.tempo,
            )

        def ao_etapa(nome, dados=None):
            if nome == "resumo":
                ponte.emitir("resumo", resumo=_resumo(dados))
            else:
                ponte.emitir("etapa", etapa=nome)

        resultados, relatorio = lote.processar_lote(
            self.context, self.aba_sigef, validos,
            ao_mudar=ao_mudar, deve_parar=self.parar_lote.is_set, ao_etapa=ao_etapa,
            documentos=documentos,
        )
        ponte.emitir(
            "lote_fim", relatorio=relatorio,
            resultados=[
                {**_item_para_tela(r.item), "estado": r.estado, "mensagem": r.mensagem,
                 "avisos": r.avisos, "pasta": r.pasta, "tempo": r.tempo}
                for r in resultados
            ],
        )

    def _soltar(self) -> None:
        if self.playwright is not None:
            try:
                self.playwright.stop()
            except Exception:
                pass
        self.playwright = self.browser = self.context = self.aba_sigef = None


def _resumo(dados: dict) -> dict:
    """O pacote do download, só com o que a tela mostra."""
    nomes = lambda caminhos: [os.path.basename(c) for c in caminhos]  # noqa: E731
    return {
        "ob": dados.get("ob"),
        "pasta": dados.get("pasta_processo"),
        # Uma entrada por CE DISTINTA: cada uma vira um documento no SEI.
        "ces": [
            {"numero": numero, "paginas": len(arquivos)}
            for numero, arquivos in dados.get("grupos_ce", [])
        ],
        "obs": nomes(dados.get("arquivos_ob", [])),
        # Os tipos marcados na janela (pacote antigo, sem a chave: todos).
        "documentos": list(normalizar_documentos(dados.get("documentos"))),
        "lancamentos": [
            {
                "pp": item.get("pp"),
                "ce": item.get("numero_ce"),
                "valor": item.get("valor"),
                "ok": bool(item.get("anexo_baixado")),
                "arquivos": nomes(item.get("arquivos_anexar", [])),
            }
            for item in dados.get("lancamentos", [])
        ],
    }


def _item_para_tela(item) -> dict:
    return {
        "linha": item.linha, "processo": item.processo, "ob": item.ob,
        "tipo": _chave_do_tipo(item.tipo_ob), "erro": item.erro,
        "ja_concluida": item.ja_concluida, "original": item.original,
    }


trabalhador = Trabalhador()


_dare = {"modulo": None}


def _modulo_dare():
    """O módulo DARE (janela/modulo_dare.py), importado e ligado à janela na 1ª vez."""
    if _dare["modulo"] is None:
        from janela import modulo_dare

        modulo_dare.configurar(ponte.emitir, lambda: ponte.janela)
        _dare["modulo"] = modulo_dare
    return _dare["modulo"]


# --------------------------------------------- O que a janela pode chamar


class Api:
    """Métodos expostos ao JS como window.pywebview.api.<nome>()."""

    def estado_inicial(self) -> dict:
        sessao = carregar_sessao()
        return {
            "versao": VERSAO,
            "pasta": PASTA_BASE,
            "processo": sessao.get("processo") or "",
            "ob": sessao.get("ob") or "",
            "tipo_ob": _chave_do_tipo(sessao.get("tipo_ob")),
            "tipos_ob": TIPOS_OB,
        }

    def __init__(self):
        # A última lista lida (planilha ou texto colado), e de onde veio:
        # trocar o tipo padrão relê a mesma fonte.
        self._itens = []
        self._fonte = None

    def conectar(self) -> None:
        trabalhador.comandos.put(("conectar", {}))

    def login_confirmado(self) -> None:
        trabalhador.comandos.put(("apos_login", {}))

    def validar_processo(self, texto: str):
        return normalizar_processo_sei(texto or "")

    @staticmethod
    def _documentos_escolhidos(documentos):
        """
        As caixas CE/NL/PP/OB marcadas no passo 3, ou None se nenhuma
        válida veio marcada. Sem a lista (janela antiga): todos.
        """
        if documentos is None:
            return DOCUMENTOS
        if not any(str(d).strip().upper() in DOCUMENTOS for d in documentos):
            return None
        return normalizar_documentos(documentos)

    def processar(self, processo: str, ob: str, tipo_ob: str = None, documentos=None) -> dict:
        normalizado = normalizar_processo_sei(processo or "")
        ob = (ob or "").strip().upper()
        if not normalizado:
            return {"ok": False, "campo": "processo"}
        if not any(c.isdigit() for c in ob):
            return {"ok": False, "campo": "ob"}
        if tipo_ob not in TIPOS_OB:
            return {"ok": False, "campo": "tipo"}
        escolhidos = self._documentos_escolhidos(documentos)
        if not escolhidos:
            return {"ok": False, "campo": "documentos"}
        trabalhador.comandos.put(
            ("processar", {"processo": normalizado, "ob": ob, "tipo_ob": TIPOS_OB[tipo_ob],
                           "documentos": list(escolhidos)})
        )
        return {"ok": True, "processo": normalizado, "ob": ob, "tipo_ob": tipo_ob,
                "documentos": list(escolhidos)}

    # ---- lote ----

    def _ler(self, tipo_padrao: str) -> dict:
        tipo = TIPOS_OB.get(tipo_padrao, etapa_sei2.TEXTO_LINK_OB_REGULARIZACAO)
        origem, valor = self._fonte or ("texto", "")
        try:
            self._itens = lote.ler_arquivo(valor, tipo) if origem == "arquivo" else lote.ler_texto(valor, tipo)
        except Exception as erro:  # planilha corrompida, .xls antigo, arquivo aberto em outro programa
            self._itens = []
            return {"ok": False, "erro": str(erro) or type(erro).__name__, "arquivo": valor if origem == "arquivo" else ""}
        return {
            "ok": True,
            "arquivo": os.path.basename(valor) if origem == "arquivo" else "",
            "itens": [_item_para_tela(item) for item in self._itens],
        }

    def ler_lote_texto(self, texto: str, tipo_padrao: str) -> dict:
        self._fonte = ("texto", texto or "")
        return self._ler(tipo_padrao)

    def escolher_planilha(self, tipo_padrao: str):
        import webview

        escolhido = ponte.janela.create_file_dialog(
            webview.FileDialog.OPEN,
            file_types=("Planilhas e listas (*.xlsx;*.csv;*.txt)", "Todos os arquivos (*.*)"),
        )
        if not escolhido:
            return None  # cancelou
        self._fonte = ("arquivo", escolhido[0])
        return self._ler(tipo_padrao)

    def reler_lote(self, tipo_padrao: str) -> dict:
        return self._ler(tipo_padrao)

    def processar_lote(self, somente_linhas=None, documentos=None) -> dict:
        """
        Roda a última lista lida. `somente_linhas` refaz só essas (os que
        deram erro). `documentos`: as caixas CE/NL/PP/OB marcadas.
        """
        escolhidos = self._documentos_escolhidos(documentos)
        if not escolhidos:
            return {"ok": False, "campo": "documentos"}
        itens = [item for item in self._itens if item.valido]
        if somente_linhas:
            linhas = set(somente_linhas)
            itens = [item for item in itens if item.linha in linhas]
        # Confere de novo: numa segunda rodada da mesma lista (continuar
        # depois de um erro), o que já terminou tem que ser pulado.
        for item in itens:
            item.ja_concluida = etapa_sei2.ob_ja_concluida(item.processo, item.ob)
        if not itens:
            return {"ok": False}
        trabalhador.comandos.put(("lote", {"itens": itens, "documentos": list(escolhidos)}))
        return {"ok": True, "quantidade": len(itens)}

    def parar_lote(self) -> None:
        trabalhador.parar_lote.set()

    def abrir_arquivo(self, caminho: str) -> None:
        if caminho and os.path.exists(caminho):
            os.startfile(caminho)

    def responder(self, texto: str = "") -> None:
        _respostas.put(texto or "")

    def fechar(self) -> None:
        ponte.janela.destroy()

    def abrir_pasta(self, caminho: str = "") -> None:
        alvo = caminho if caminho and os.path.isdir(caminho) else PASTA_BASE
        os.startfile(alvo)

    # ---- Banco do Brasil ----
    # Cada chamada que importa o módulo pela primeira vez pode demorar um
    # pouco (Excel/COM, pyautogui); o JS mostra "carregando" enquanto isso.

    def _erro_modulo(self, erro: Exception) -> dict:
        print(traceback.format_exc())
        return {"ok": False, "erro": f"{type(erro).__name__}: {erro}"}

    def bb_estado(self) -> dict:
        try:
            return {"ok": True, **modulos_janela.bb_estado()}
        except Exception as erro:
            return self._erro_modulo(erro)

    def bb_executar(self, valores: dict, indice, respostas: dict = None) -> dict:
        try:
            return modulos_janela.bb_executar(valores or {}, int(indice), ponte.emitir, respostas or {})
        except Exception as erro:
            return self._erro_modulo(erro)

    def bb_responder(self, texto: str = "") -> None:
        modulos_janela.bb_responder(texto or "")

    def modulo_parar(self) -> None:
        modulos_janela.parar()

    def abas_planilha(self, caminho: str) -> list:
        return modulos_janela.abas_da_planilha(caminho or "")

    def escolher_planilha_modulo(self):
        """Janela de 'abrir arquivo' para a planilha do BB."""
        import webview

        escolhido = ponte.janela.create_file_dialog(
            webview.FileDialog.OPEN,
            file_types=("Planilhas (*.xlsx;*.xlsm;*.csv)", "Todos os arquivos (*.*)"),
        )
        if not escolhido:
            return None
        caminho = escolhido[0]
        return {"caminho": caminho, "abas": modulos_janela.abas_da_planilha(caminho)}

    # ---- DARE ----
    # Uma porta só: a página DARE (interface/dare.js) chama dare("acao", {...}).
    # O módulo só é carregado na primeira chamada -- quem não usa o DARE não
    # paga o tempo de importar.

    def dare(self, acao: str, dados: dict = None) -> dict:
        try:
            return _modulo_dare().chamar(acao, dados or {})
        except Exception as erro:
            return self._erro_modulo(erro)

    # ---- relatório gerencial ----

    def opcoes_relatorio(self) -> dict:
        """Valores para abrir a caixa do relatório: mês corrente e o último tempo manual usado."""
        hoje = date.today()
        return {
            "de": hoje.replace(day=1).isoformat(),
            "ate": hoje.isoformat(),
            "minutos_manual": _ler_config().get("minutos_manual_por_ob", 20),
        }

    def gerar_relatorio(self, de: str, ate: str, minutos_manual) -> dict:
        try:
            minutos = float(str(minutos_manual).replace(",", "."))
            if minutos <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return {"ok": False, "erro": "Informe quantos minutos leva uma OB feita à mão (ex.: 20)."}
        try:
            inicio, fim = date.fromisoformat(de), date.fromisoformat(ate)
        except (TypeError, ValueError):
            return {"ok": False, "erro": "Confira as datas do período."}
        _gravar_config(minutos_manual_por_ob=minutos)
        try:
            caminho = relatorio_gerencial.gerar(inicio, fim, minutos)
        except Exception as erro:  # planilha de métricas travada/corrompida
            print(traceback.format_exc())
            return {"ok": False, "erro": f"Não consegui montar o relatório: {erro}"}
        os.startfile(caminho)
        return {"ok": True, "caminho": caminho}


HTML_ATIVACAO = """<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<style>
 body{font-family:Segoe UI,Arial,sans-serif;background:#F4F6F9;color:#1f2a37;margin:0;padding:28px}
 h1{font-size:20px;margin:0 0 6px} p{margin:6px 0 14px;color:#4b5563;font-size:14px}
 .codigo{display:flex;gap:10px;align-items:center;margin:8px 0 18px}
 .codigo b{font-family:Consolas,monospace;font-size:24px;letter-spacing:2px;background:#fff;
   border:1px solid #d1d5db;border-radius:8px;padding:8px 14px}
 textarea{width:100%;box-sizing:border-box;height:96px;font-family:Consolas,monospace;font-size:12px;
   border:1px solid #d1d5db;border-radius:8px;padding:8px}
 button{background:#0b3d91;color:#fff;border:0;border-radius:8px;padding:9px 18px;font-size:14px;cursor:pointer}
 button.sec{background:#e5e7eb;color:#1f2a37}
 #msg{margin-top:12px;font-size:14px;min-height:20px} .erro{color:#b91c1c} .ok{color:#15803d}
</style></head><body>
<h1>Ativação do programa</h1>
<p id="motivo"></p>
<p>Envie este <b>código da máquina</b> para quem administra as licenças:</p>
<div class="codigo"><b id="codigo">...</b><button class="sec" onclick="copiar()">Copiar</button></div>
<p>Depois, cole aqui a chave de licença recebida:</p>
<textarea id="chave" placeholder="SIGEFSEI-..."></textarea>
<div style="margin-top:12px"><button onclick="ativar()">Ativar</button></div>
<div id="msg"></div>
<script>
 function msg(t, c){ const m=document.getElementById('msg'); m.textContent=t; m.className=c||''; }
 window.addEventListener('pywebviewready', async () => {
   const e = await pywebview.api.estado();
   document.getElementById('codigo').textContent = e.codigo;
   document.getElementById('motivo').textContent = 'Licença: ' + e.motivo + '.';
 });
 async function copiar(){ const r = await pywebview.api.copiar_codigo();
   msg(r ? 'Código copiado.' : 'Selecione o código e copie com Ctrl+C.', r ? 'ok' : ''); }
 async function ativar(){
   const t = document.getElementById('chave').value;
   if(!t.trim()){ msg('Cole a chave recebida.', 'erro'); return; }
   if(!window.pywebview || !pywebview.api || !pywebview.api.ativar){
     msg('A janela ainda está carregando. Aguarde um instante e clique de novo.', 'erro'); return; }
   msg('Conferindo...');
   // Nunca mais "Conferindo..." para sempre: erro do Python ou 20s sem
   // resposta aparecem na tela.
   const limite = new Promise((_, falha) => setTimeout(
     () => falha(new Error('o programa não respondeu em 20 segundos')), 20000));
   try {
     const r = await Promise.race([pywebview.api.ativar(t), limite]);
     if(r && r.ok){ msg('Licença ativada para ' + r.nome + ' até ' + r.validade + '. Abrindo o programa...', 'ok'); }
     else { msg((r && r.erro) || 'Não ativou.', 'erro'); }
   } catch(e) {
     msg('Não foi possível ativar: ' + (e && e.message ? e.message : e) + '. Feche e abra o programa e tente de novo.', 'erro');
   }
 }
</script></body></html>"""


def _titulo_com_licenca(situacao: dict) -> str:
    titulo = "Central de Automações"
    if situacao.get("valida"):
        titulo += f"  —  licenciado para {situacao['nome']} até {situacao['validade']}"
    return titulo


def _confirmar_fechar() -> bool:
    """
    Fechar a janela com o DARE processando: pergunta antes, como o aplicativo
    DARE fazia. False cancela o fechamento (evento "closing" do pywebview, que
    roda na thread da janela -- por isso a caixa nativa do Windows).
    """
    modulo = _dare["modulo"]
    if modulo is None or not modulo.executando() or os.name != "nt":
        return True
    import ctypes

    texto = ("Há lançamentos do DARE sendo processados agora.\n\n"
             "Se fechar, o lançamento atual pode ficar pela metade. Os que não foram concluídos "
             "ficam guardados como pendentes.\n\nFechar mesmo assim?")
    # MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2 | MB_TASKMODAL; IDYES = 6
    try:
        return ctypes.windll.user32.MessageBoxW(None, texto, "Central de Automações", 0x4 | 0x30 | 0x100 | 0x2000) == 6
    except Exception:  # noqa: BLE001 - sem a caixa, fecha como antes
        return True


def _criar_janela_principal(webview, situacao: dict):
    trabalhador.start()
    janela = webview.create_window(
        _titulo_com_licenca(situacao),
        url=os.path.join(PASTA_INTERFACE, "index.html"),
        js_api=Api(),
        width=1120,
        height=760,
        min_size=(900, 640),
        background_color="#F4F6F9",
        text_select=True,
    )
    ponte.janela = janela
    try:
        janela.events.closing += _confirmar_fechar
    except AttributeError:  # pywebview sem eventos: fecha sem perguntar
        pass
    if situacao.get("aviso"):
        print(f"⚠️  {situacao['aviso']}")
    return janela


class ApiAtivacao:
    """
    Janela de ativação: aparece no lugar da principal enquanto não houver licença.

    ATENÇÃO: nada de atributo PÚBLICO guardando objetos do pywebview. Ele
    percorre os atributos públicos da js_api para expor ao JavaScript; com a
    janela num atributo público ele entrava em janela.native..., recursão
    infinita, e a ponte JS -> Python nunca ficava pronta ("Conferindo..."
    para sempre). Por isso _webview e _janela.
    """

    def __init__(self, webview):
        self._webview = webview
        self._janela = None

    def estado(self) -> dict:
        return licenca.estado()

    def copiar_codigo(self) -> bool:
        try:
            import pyperclip
            pyperclip.copy(licenca.codigo_da_maquina())
            return True
        except Exception:
            return False

    def ativar(self, texto: str) -> dict:
        try:
            situacao = licenca.ativar(texto)
        except licenca.ErroLicenca as erro:
            return {"ok": False, "erro": f"Não ativou: {erro}."}
        except Exception as erro:
            _registrar_erro_ativacao()
            return {"ok": False, "erro": f"Erro inesperado ao conferir a chave: {erro}"}
        try:
            # Primeiro abre a principal, depois fecha esta: fechar a única
            # janela aberta encerraria o programa.
            _criar_janela_principal(self._webview, situacao)
            threading.Timer(1.5, self._janela.destroy).start()
        except Exception as erro:
            _registrar_erro_ativacao()
            return {"ok": False, "erro": f"Licença ativada, mas a janela principal não abriu "
                                         f"({erro}). Feche e abra o programa de novo."}
        return {"ok": True, "nome": situacao["nome"], "validade": situacao["validade"]}


def _registrar_erro_ativacao() -> None:
    try:
        os.makedirs(licenca.PASTA_LICENCA, exist_ok=True)
        with open(os.path.join(licenca.PASTA_LICENCA, "erro_ativacao.log"), "a",
                  encoding="utf-8") as arquivo:
            arquivo.write(f"--- {time.strftime('%d/%m/%Y %H:%M:%S')}\n{traceback.format_exc()}\n")
    except OSError:
        pass


def main() -> None:
    import webview

    situacao = licenca.estado()
    if situacao["valida"]:
        _criar_janela_principal(webview, situacao)
    else:
        api = ApiAtivacao(webview)
        api._janela = webview.create_window(
            "Central de Automações — ativação", html=HTML_ATIVACAO, js_api=api,
            width=640, height=520, resizable=False, background_color="#F4F6F9",
            text_select=True,
        )
    # Guarda o estado da janela (WebView2) fora da pasta de dados.
    pasta_janela = os.path.join(
        os.environ.get("LOCALAPPDATA", PASTA_BASE), "Automacao SIGEF-SEI", "janela"
    )
    # Antes de a janela abrir: sem isso o WebView2 pode mostrar a tela da
    # versão anterior (ver janela/cache_janela.py).
    cache_janela.limpar(pasta_janela)
    webview.start(private_mode=False, storage_path=pasta_janela)

    # Janela fechada: destrava quem estiver esperando resposta e solta o
    # Chrome. O Chrome em si continua aberto, como no main.py.
    _respostas.put(None)
    if trabalhador.is_alive():
        trabalhador.comandos.put(("sair", {}))
        trabalhador.join(timeout=3)
    os._exit(0)


if __name__ == "__main__":
    main()
