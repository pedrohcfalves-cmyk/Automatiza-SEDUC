"""
Desempenho e diagnóstico do sistema (aba "Desempenho" do aplicativo), para estudo e apresentação.

  diagnosticar()          -> checagem do computador, dos componentes e da rede (DARE e SEI)
  BENCHMARKS / rodar_benchmarks() -> testes de velocidade (CPU, disco, memória, rede)
  Monitor                 -> amostras de uso de CPU/memória/disco/rede em tempo real
  analisar_automacao()    -> estatísticas dos tempos reais de cada etapa (dados/desempenho.csv)
  gerar_relatorio_html()  -> relatório completo, imprimível, com gráficos

Nada aqui depende da janela: tudo pode ser testado e usado em scripts.
"""

import csv
import hashlib
import json
import logging
import os
import platform
import random
import re
import shutil
import socket
import ssl
import statistics
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Callable

from . import __version__, config, navegador, planilha, utils

try:
    import psutil
except ImportError:  # pragma: no cover - o aplicativo empacotado sempre traz o psutil
    psutil = None

log = logging.getLogger("dare.desempenho")

OK, AVISO, ERRO, INFO = "ok", "aviso", "erro", "info"


# ---- Estatística --------------------------------------------------------------------------

@dataclass
class Estatisticas:
    n: int = 0
    media: float = 0.0
    mediana: float = 0.0
    desvio: float = 0.0
    minimo: float = 0.0
    maximo: float = 0.0
    p95: float = 0.0
    cv: float = 0.0  # coeficiente de variação (%) = desvio / média

    @classmethod
    def de(cls, valores: list[float]) -> "Estatisticas":
        v = sorted(x for x in valores if x is not None)
        if not v:
            return cls()
        media = statistics.fmean(v)
        desvio = statistics.stdev(v) if len(v) > 1 else 0.0
        return cls(
            n=len(v), media=media, mediana=statistics.median(v), desvio=desvio,
            minimo=v[0], maximo=v[-1], p95=percentil(v, 95),
            cv=(desvio / media * 100) if media else 0.0,
        )


def percentil(valores_ordenados: list[float], p: float) -> float:
    """Percentil com interpolação linear (mesmo método do Excel PERCENTIL.INC)."""
    v = valores_ordenados
    if not v:
        return 0.0
    if len(v) == 1:
        return v[0]
    pos = (len(v) - 1) * p / 100
    baixo = int(pos)
    alto = min(baixo + 1, len(v) - 1)
    return v[baixo] + (v[alto] - v[baixo]) * (pos - baixo)


def num_br(valor: float, casas: int = 2) -> str:
    """1234.5 -> '1.234,50'."""
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _float_br(texto: str) -> float | None:
    texto = (texto or "").strip()
    if not texto:
        return None
    try:
        return float(texto.replace(".", "").replace(",", ".")) if "," in texto else float(texto)
    except ValueError:
        return None


# ---- Diagnóstico --------------------------------------------------------------------------

@dataclass
class ItemDiagnostico:
    grupo: str
    nome: str
    valor: str
    status: str = INFO  # ok | aviso | erro | info
    detalhe: str = ""


def _nome_processador() -> str:
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as chave:
                return str(winreg.QueryValueEx(chave, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for linha in f:
                if linha.lower().startswith("model name"):
                    return linha.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine() or "desconhecido"


def versao_navegador(exe: str | None) -> str:
    """Versão do Chrome/Edge sem abri-lo: a pasta do executável tem uma subpasta com a versão."""
    if not exe:
        return ""
    try:
        pasta = Path(exe).parent
        versoes = [p.name for p in pasta.iterdir() if p.is_dir() and re.fullmatch(r"\d+(\.\d+){3}", p.name)]
        if versoes:
            return max(versoes, key=lambda v: tuple(int(x) for x in v.split(".")))
    except OSError:
        pass
    return ""


def _versao_pacote(nome: str) -> str:
    try:
        from importlib.metadata import version
        return version(nome)
    except Exception:  # noqa: BLE001
        return ""


def _excel_instalado() -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Excel.Application\CLSID"):
            return True
    except OSError:
        return False


@dataclass
class TempoConexao:
    host: str
    dns_ms: float = 0.0
    tcp_ms: float = 0.0
    tls_ms: float = 0.0
    resposta_ms: float = 0.0  # do pedido até o 1º byte (TTFB)
    total_ms: float = 0.0
    status_http: str = ""
    erro: str = ""


def medir_conexao(host: str, timeout: float = 6.0) -> TempoConexao:
    """Mede as fases de uma requisição HTTPS: DNS, TCP, TLS e tempo até o 1º byte."""
    r = TempoConexao(host)
    inicio = time.perf_counter()
    sock = None
    try:
        t = time.perf_counter()
        endereco = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)[0][4]
        r.dns_ms = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        sock = socket.create_connection(endereco[:2], timeout=timeout)
        r.tcp_ms = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        contexto = ssl.create_default_context()
        sock = contexto.wrap_socket(sock, server_hostname=host)
        r.tls_ms = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        sock.sendall(f"HEAD / HTTP/1.1\r\nHost: {host}\r\nUser-Agent: DARE-diagnostico\r\n"
                     "Connection: close\r\n\r\n".encode())
        primeira = sock.recv(64).decode("latin-1", "replace")
        r.resposta_ms = (time.perf_counter() - t) * 1000
        r.status_http = primeira.split("\r\n", 1)[0][9:12] if primeira.startswith("HTTP/") else "?"
    except Exception as exc:  # noqa: BLE001
        r.erro = f"{type(exc).__name__}: {exc}"[:160]
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
    r.total_ms = (time.perf_counter() - inicio) * 1000
    return r


def _testar_motor_automacao() -> ItemDiagnostico:
    """Liga e desliga o motor do Playwright (sem abrir navegador): confirma que o componente funciona."""
    try:
        from playwright.sync_api import sync_playwright
        inicio = time.perf_counter()
        with sync_playwright() as p:
            _ = p.chromium  # o motor respondeu
        seg = time.perf_counter() - inicio
        return ItemDiagnostico("Componentes", "Motor de automação", f"pronto em {num_br(seg)} s",
                               OK if seg < 10 else AVISO, "O Playwright iniciou e encerrou normalmente.")
    except Exception as exc:  # noqa: BLE001
        return ItemDiagnostico("Componentes", "Motor de automação", "não iniciou", ERRO, f"{type(exc).__name__}: {exc}"[:200])


def diagnosticar(incluir_rede: bool = True) -> list[ItemDiagnostico]:
    itens: list[ItemDiagnostico] = []
    add = itens.append

    # Sistema
    add(ItemDiagnostico("Sistema", "Sistema operacional",
                        f"{platform.system()} {platform.release()} ({platform.machine()})",
                        INFO, platform.version()))
    nucleos_fisicos = psutil.cpu_count(logical=False) if psutil else None
    nucleos = os.cpu_count() or 0
    add(ItemDiagnostico("Sistema", "Processador", _nome_processador(), INFO,
                        f"{nucleos_fisicos or '?'} núcleos físicos · {nucleos} lógicos"))
    if psutil:
        mem = psutil.virtual_memory()
        livre_gb = mem.available / 1024 ** 3
        add(ItemDiagnostico("Sistema", "Memória RAM",
                            f"{num_br(mem.total / 1024 ** 3, 1)} GB (livre: {num_br(livre_gb, 1)} GB)",
                            OK if livre_gb >= 1 else AVISO,
                            "" if livre_gb >= 1 else "Pouca memória livre: feche programas abertos."))
        try:
            inicio_sistema = datetime.fromtimestamp(psutil.boot_time())
            horas = (datetime.now() - inicio_sistema).total_seconds() / 3600
            add(ItemDiagnostico("Sistema", "Tempo ligado", f"{num_br(horas, 1)} h",
                                OK if horas < 24 * 7 else AVISO,
                                "" if horas < 24 * 7 else "Reiniciar o computador pode deixá-lo mais rápido."))
        except Exception:  # noqa: BLE001
            pass
    try:
        config.BASE_DADOS.mkdir(parents=True, exist_ok=True)
        uso = shutil.disk_usage(config.BASE_DADOS)
        livre = uso.free / 1024 ** 3
        add(ItemDiagnostico("Sistema", "Disco (pasta de dados)",
                            f"{num_br(livre, 1)} GB livres de {num_br(uso.total / 1024 ** 3, 0)} GB",
                            OK if livre >= 2 else (AVISO if livre >= 0.5 else ERRO), str(config.BASE_DADOS)))
    except OSError as exc:
        add(ItemDiagnostico("Sistema", "Disco (pasta de dados)", "inacessível", ERRO, str(exc)))

    # Aplicativo e componentes
    add(ItemDiagnostico("Componentes", "DARE Automação", f"versão {__version__}", OK,
                        "executável" if config.EMPACOTADO else f"código-fonte · Python {sys.version.split()[0]}"))
    v_pw = _versao_pacote("playwright")
    add(ItemDiagnostico("Componentes", "Playwright (automação)", v_pw or "não instalado",
                        OK if v_pw else ERRO, "" if v_pw else "Necessário para gerar e anexar os DAREs."))
    if v_pw:
        add(_testar_motor_automacao())
    exe = navegador.localizar_chrome()
    if exe:
        nome = navegador.nome_navegador(exe)
        versao = versao_navegador(exe)
        add(ItemDiagnostico("Componentes", "Navegador", f"{nome} {versao}".strip(),
                            OK if "Chrome" in nome else AVISO,
                            exe if "Chrome" in nome else f"Chrome não encontrado; usando o Edge. {exe}"))
    else:
        add(ItemDiagnostico("Componentes", "Navegador", "não encontrado", ERRO,
                            "Instale o Google Chrome ou defina DARE_CHROME_PATH."))
    ativo = navegador.chrome_debug_ativo()
    add(ItemDiagnostico("Componentes", f"Porta de depuração ({config.PORTA_CDP})",
                        "aberta" if ativo else "fechada", OK if ativo else INFO,
                        "" if ativo else "Normal se o navegador do programa ainda não foi aberto."))
    try:
        import win32com.client  # noqa: F401
        tem_pywin32 = True
    except ImportError:
        tem_pywin32 = False
    excel = _excel_instalado()
    add(ItemDiagnostico("Componentes", "Microsoft Excel (modo planilha)",
                        "instalado" if excel and tem_pywin32 else "não disponível",
                        OK if excel and tem_pywin32 else AVISO,
                        "" if excel and tem_pywin32 else "Sem o Excel, arquivos .xlsx/.xlsm são lidos diretamente."))
    v_xl = _versao_pacote("openpyxl")
    add(ItemDiagnostico("Componentes", "Leitura de .xlsx sem Excel", v_xl or "não instalado",
                        OK if v_xl else AVISO))
    v_ps = _versao_pacote("psutil")
    add(ItemDiagnostico("Componentes", "Monitor do sistema (psutil)", v_ps or "não instalado",
                        OK if v_ps else AVISO))

    # Rede
    if incluir_rede:
        for rotulo, host in (("Site do DARE", config.HOST_DARE), ("Site do SEI", config.HOST_SEI)):
            t = medir_conexao(host)
            if t.erro:
                add(ItemDiagnostico("Rede", rotulo, "sem conexão", ERRO, f"{host} · {t.erro}"))
                continue
            status = OK if t.total_ms < 1500 else AVISO
            add(ItemDiagnostico(
                "Rede", rotulo, f"{num_br(t.total_ms, 0)} ms", status,
                f"DNS {num_br(t.dns_ms, 0)} · TCP {num_br(t.tcp_ms, 0)} · TLS {num_br(t.tls_ms, 0)} · "
                f"resposta {num_br(t.resposta_ms, 0)} ms · HTTP {t.status_http}",
            ))

    # Dados
    from . import limpeza
    qtd, tam = limpeza.tamanho_pasta()
    add(ItemDiagnostico("Dados", "Pasta dos PDFs", f"{qtd} PDF(s) · {limpeza.formatar_bytes(tam)}",
                        OK if tam < 1024 ** 3 else AVISO, str(config.PASTA_PDF)))
    try:
        with open(config.ARQ_HISTORICO, encoding="utf-8-sig") as f:
            registros = max(0, sum(1 for _ in f) - 1)
    except OSError:
        registros = 0
    add(ItemDiagnostico("Dados", "Histórico de execuções", f"{registros} registro(s)", INFO,
                        str(config.ARQ_HISTORICO)))
    return itens


# ---- Benchmarks ---------------------------------------------------------------------------

@dataclass
class ResultadoBenchmark:
    chave: str
    nome: str
    valor: float
    unidade: str
    detalhe: str = ""
    maior_melhor: bool = True


def _cpf_aleatorio(rnd: random.Random) -> str:
    base = [rnd.randint(0, 9) for _ in range(9)]
    for n in (9, 10):
        soma = sum(d * (n + 1 - i) for i, d in enumerate(base))
        base.append((soma * 10 % 11) % 10)
    return "".join(map(str, base))


def bench_validacao(duracao: float = 1.0) -> ResultadoBenchmark:
    """CPU (1 núcleo): quantas validações de CPF/CNPJ por segundo (o que o programa faz em cada linha)."""
    rnd = random.Random(42)
    cpfs = [_cpf_aleatorio(rnd) for _ in range(500)]
    feitos, inicio = 0, time.perf_counter()
    while time.perf_counter() - inicio < duracao:
        for c in cpfs:
            utils.validar_cpf(c)
            utils.validar_cnpj("11222333000181")
        feitos += len(cpfs) * 2
    seg = time.perf_counter() - inicio
    return ResultadoBenchmark("cpu_validacao", "CPU · validação de CPF/CNPJ", feitos / seg,
                              "validações/s", f"{num_br(feitos, 0)} validações em {num_br(seg)} s")


def bench_hash(mb: int = 32) -> ResultadoBenchmark:
    """CPU: velocidade de cálculo SHA-256 (processamento intensivo de dados)."""
    dados = os.urandom(1024 * 1024)
    inicio = time.perf_counter()
    h = hashlib.sha256()
    for _ in range(mb):
        h.update(dados)
    seg = time.perf_counter() - inicio
    return ResultadoBenchmark("cpu_hash", "CPU · SHA-256", mb / seg, "MB/s", f"{mb} MB em {num_br(seg, 3)} s")


def bench_planilha(linhas: int = 2000) -> ResultadoBenchmark:
    """Leitura e validação de uma planilha simulada (modo planilha, sem Excel)."""
    rnd = random.Random(7)
    dados = [["Processo SEI", "CNPJ", "CPF", "Recolhedor", "Referência", "Vencimento", "Valor"]]
    for i in range(linhas):
        dados.append([f"0029.{i:06d}/2026-12", "11222333000181", _cpf_aleatorio(rnd), "11222333000181",
                      "102026", datetime(2026, 11, 10), round(rnd.uniform(50, 9000), 2)])
    tabela = planilha.TabelaMemoria(dados)
    inicio = time.perf_counter()
    linha_cab = planilha.detectar_linha_cabecalho(tabela)
    mapa = planilha.Mapeamento(planilha.sugerir_mapeamento(planilha.ler_cabecalhos(tabela, linha_cab)), linha_cab)
    resultado = planilha.ler_lotes(tabela, mapa, 2, linhas + 1)
    seg = time.perf_counter() - inicio
    return ResultadoBenchmark("planilha", "Leitura de planilha (simulada)", len(resultado.lotes) / seg,
                              "linhas/s", f"{len(resultado.lotes)} linhas válidas em {num_br(seg, 3)} s")


def bench_memoria(mb: int = 128) -> ResultadoBenchmark:
    """Memória: cópia de um bloco grande (largura de banda aproximada)."""
    origem = bytearray(mb * 1024 * 1024)
    inicio = time.perf_counter()
    for _ in range(4):
        copia = bytes(origem)
    seg = time.perf_counter() - inicio
    del copia, origem
    return ResultadoBenchmark("memoria", "Memória · cópia", (mb * 4 / 1024) / seg, "GB/s",
                              f"{mb * 4} MB copiados em {num_br(seg, 3)} s")


def bench_disco(pasta: Path | None = None, mb: int = 64) -> list[ResultadoBenchmark]:
    """Disco: escrita e leitura sequenciais + criação de arquivos do tamanho de um PDF de DARE."""
    pasta = Path(pasta or config.BASE_DADOS)
    pasta.mkdir(parents=True, exist_ok=True)
    resultados = []
    bloco = os.urandom(1024 * 1024)
    with tempfile.TemporaryDirectory(dir=pasta, prefix="bench_") as tmp:
        arq = Path(tmp) / "teste.bin"
        inicio = time.perf_counter()
        with open(arq, "wb", buffering=0) as f:
            for _ in range(mb):
                f.write(bloco)
            os.fsync(f.fileno())
        seg = time.perf_counter() - inicio
        resultados.append(ResultadoBenchmark("disco_escrita", "Disco · escrita sequencial", mb / seg, "MB/s",
                                             f"{mb} MB gravados (com fsync) em {num_br(seg, 3)} s"))
        inicio = time.perf_counter()
        with open(arq, "rb", buffering=0) as f:
            while f.read(1024 * 1024):
                pass
        seg = time.perf_counter() - inicio
        resultados.append(ResultadoBenchmark("disco_leitura", "Disco · leitura sequencial", mb / seg, "MB/s",
                                             "pode incluir o cache do sistema operacional"))
        arq.unlink()
        pdf = os.urandom(180 * 1024)  # um PDF de DARE tem por volta de 150-200 KB
        n = 60
        inicio = time.perf_counter()
        for i in range(n):
            caminho = Path(tmp) / f"DARE_{i}.pdf"
            caminho.write_bytes(pdf)
        for i in range(n):
            (Path(tmp) / f"DARE_{i}.pdf").unlink()
        seg = time.perf_counter() - inicio
        resultados.append(ResultadoBenchmark("disco_pdfs", "Disco · salvar e apagar PDFs", n / seg, "arquivos/s",
                                             f"{n} arquivos de 180 KB gravados e apagados em {num_br(seg, 3)} s"))
    return resultados


def bench_rede(amostras: int = 5) -> list[ResultadoBenchmark]:
    """Rede: latência (tempo de conexão TCP) até o DARE e o SEI, com variação (jitter)."""
    resultados = []
    for chave, rotulo, host in (("rede_dare", "Rede · latência DARE", config.HOST_DARE),
                                ("rede_sei", "Rede · latência SEI", config.HOST_SEI)):
        tempos = []
        erro = ""
        try:
            endereco = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)[0][4][:2]
        except OSError as exc:
            endereco, erro = None, str(exc)
        for _ in range(amostras if endereco else 0):
            t = time.perf_counter()
            try:
                with socket.create_connection(endereco, timeout=5):
                    tempos.append((time.perf_counter() - t) * 1000)
            except OSError as exc:
                erro = str(exc)
            time.sleep(0.1)
        if tempos:
            e = Estatisticas.de(tempos)
            resultados.append(ResultadoBenchmark(
                chave, rotulo, e.media, "ms",
                f"mín {num_br(e.minimo, 0)} · máx {num_br(e.maximo, 0)} · jitter {num_br(e.desvio, 1)} ms "
                f"({e.n} amostras)", maior_melhor=False))
        else:
            resultados.append(ResultadoBenchmark(chave, rotulo, 0.0, "ms", f"sem conexão: {erro}"[:120], False))
    return resultados


BENCHMARKS: list[tuple[str, Callable[[], list[ResultadoBenchmark] | ResultadoBenchmark]]] = [
    ("Validação de documentos (CPU)", bench_validacao),
    ("SHA-256 (CPU)", bench_hash),
    ("Leitura de planilha", bench_planilha),
    ("Memória", bench_memoria),
    ("Disco", bench_disco),
    ("Rede", bench_rede),
]


def rodar_benchmarks(progresso: Callable[[int, int, str], None] | None = None,
                     cancelar: Callable[[], bool] | None = None) -> list[ResultadoBenchmark]:
    resultados: list[ResultadoBenchmark] = []
    for i, (nome, funcao) in enumerate(BENCHMARKS):
        if cancelar and cancelar():
            break
        if progresso:
            progresso(i, len(BENCHMARKS), nome)
        try:
            r = funcao()
            resultados.extend(r if isinstance(r, list) else [r])
        except Exception as exc:  # noqa: BLE001
            log.warning("Benchmark '%s' falhou: %s", nome, exc)
    if progresso:
        progresso(len(BENCHMARKS), len(BENCHMARKS), "Concluído")
    return resultados


def salvar_benchmark(resultados: list[ResultadoBenchmark]) -> dict:
    """Guarda a rodada em dados/benchmarks.json (para comparar computadores e ao longo do tempo)."""
    rodada = {
        "data_hora": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "computador": platform.node(),
        "processador": _nome_processador(),
        "sistema": f"{platform.system()} {platform.release()}",
        "versao_app": __version__,
        "resultados": [asdict(r) for r in resultados],
    }
    historico = carregar_benchmarks()
    historico.append(rodada)
    config.PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    temporario = Path(f"{config.ARQ_BENCHMARKS}.tmp")
    temporario.write_text(json.dumps(historico[-200:], ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporario, config.ARQ_BENCHMARKS)
    return rodada


def carregar_benchmarks() -> list[dict]:
    try:
        dados = json.loads(config.ARQ_BENCHMARKS.read_text(encoding="utf-8"))
        return dados if isinstance(dados, list) else []
    except (OSError, ValueError):
        return []


# ---- Monitor em tempo real ----------------------------------------------------------------

class Monitor:
    """Amostras de uso do sistema. Chame amostra() a cada 1 s (ela calcula as taxas por diferença)."""

    def __init__(self):
        self.disponivel = psutil is not None
        self._processo = psutil.Process() if psutil else None
        self._anterior: tuple[float, object, object] | None = None
        self._contador = 0
        self._navegador_mb = 0.0
        if psutil:
            psutil.cpu_percent(None)  # a primeira leitura é sempre 0: descarta
            self._processo.cpu_percent(None)

    def _ram_navegador(self) -> float:
        total = 0
        for proc in psutil.process_iter(["name", "memory_info"]):
            try:
                nome = (proc.info.get("name") or "").lower()
                if nome in ("chrome.exe", "msedge.exe", "chrome", "chromium", "msedge"):
                    total += proc.info["memory_info"].rss
            except (psutil.Error, AttributeError, TypeError):
                continue
        return total / 1024 ** 2

    def amostra(self) -> dict:
        if not psutil:
            return {}
        agora = time.monotonic()
        disco = psutil.disk_io_counters() if hasattr(psutil, "disk_io_counters") else None
        rede = psutil.net_io_counters()
        taxas = {"disco_leitura": 0.0, "disco_escrita": 0.0, "rede_rx": 0.0, "rede_tx": 0.0}
        if self._anterior:
            t0, d0, r0 = self._anterior
            dt = max(1e-6, agora - t0)
            if disco and d0:
                taxas["disco_leitura"] = (disco.read_bytes - d0.read_bytes) / dt
                taxas["disco_escrita"] = (disco.write_bytes - d0.write_bytes) / dt
            if rede and r0:
                taxas["rede_rx"] = (rede.bytes_recv - r0.bytes_recv) / dt
                taxas["rede_tx"] = (rede.bytes_sent - r0.bytes_sent) / dt
        self._anterior = (agora, disco, rede)
        if self._contador % 3 == 0:  # varrer processos custa mais: a cada 3 amostras
            try:
                self._navegador_mb = self._ram_navegador()
            except Exception:  # noqa: BLE001
                pass
        self._contador += 1
        mem = psutil.virtual_memory()
        try:
            app_mb = self._processo.memory_info().rss / 1024 ** 2
            app_cpu = self._processo.cpu_percent(None) / (os.cpu_count() or 1)
            threads = self._processo.num_threads()
        except psutil.Error:
            app_mb = app_cpu = 0.0
            threads = 0
        return {
            "cpu": psutil.cpu_percent(None),
            "ram": mem.percent,
            "ram_usada_gb": (mem.total - mem.available) / 1024 ** 3,
            "app_mb": app_mb,
            "app_cpu": app_cpu,
            "threads": threads,
            "navegador_mb": self._navegador_mb,
            **taxas,
        }


# ---- Métricas da automação ----------------------------------------------------------------

def carregar_desempenho(arq: Path | None = None) -> list[dict]:
    """Linhas de dados/desempenho.csv com os números já convertidos (float ou None)."""
    arq = arq or config.ARQ_DESEMPENHO
    try:
        with open(arq, newline="", encoding="utf-8-sig") as f:
            linhas = list(csv.DictReader(f, delimiter=";"))
    except FileNotFoundError:
        return []
    except (OSError, csv.Error) as exc:
        log.warning("Não consegui ler %s (%s).", arq, exc)
        return []
    for linha in linhas:
        for chave in list(linha):
            if chave and chave.endswith("_s"):
                linha[chave] = _float_br(linha[chave])
    return linhas


@dataclass
class AnaliseAutomacao:
    lotes: int = 0
    sucessos: int = 0
    erros: int = 0
    execucoes: int = 0
    total: Estatisticas = field(default_factory=Estatisticas)
    dare: Estatisticas = field(default_factory=Estatisticas)
    sei: Estatisticas = field(default_factory=Estatisticas)
    conexao: Estatisticas = field(default_factory=Estatisticas)
    etapas: dict[str, Estatisticas] = field(default_factory=dict)
    lotes_por_hora: float = 0.0
    gargalo: str = ""
    ultimos_totais: list[float] = field(default_factory=list)  # para o gráfico de linha

    @property
    def taxa_sucesso(self) -> float:
        return self.sucessos / self.lotes * 100 if self.lotes else 0.0


def analisar_automacao(linhas: list[dict] | None = None, apenas_sucesso: bool = True) -> AnaliseAutomacao:
    """
    Estatísticas dos tempos reais. Por padrão os tempos usam só os lotes com SUCESSO (um lote
    que falhou no meio tem tempos incompletos e distorceria as médias); contagens usam todos.
    """
    from .motor import ETAPAS  # import local: evita importar o Playwright sem necessidade

    linhas = carregar_desempenho() if linhas is None else linhas
    a = AnaliseAutomacao(lotes=len(linhas))
    a.sucessos = sum(1 for l in linhas if l.get("status") == "SUCESSO")
    a.erros = a.lotes - a.sucessos
    a.execucoes = len({l.get("execucao") for l in linhas})
    base = [l for l in linhas if l.get("status") == "SUCESSO"] if apenas_sucesso else linhas

    def coluna(nome: str) -> list[float]:
        return [l[nome] for l in base if isinstance(l.get(nome), float)]

    a.total = Estatisticas.de(coluna("total_s"))
    a.dare = Estatisticas.de(coluna("dare_s"))
    a.sei = Estatisticas.de(coluna("sei_s"))
    a.conexao = Estatisticas.de([l["conexao_s"] for l in linhas if isinstance(l.get("conexao_s"), float)])
    for chave, _, _ in ETAPAS:
        e = Estatisticas.de(coluna(f"{chave}_s"))
        if e.n:
            a.etapas[chave] = e
    if a.etapas:
        a.gargalo = max(a.etapas, key=lambda c: a.etapas[c].media)
    if a.total.media:
        a.lotes_por_hora = 3600 / a.total.media
    a.ultimos_totais = coluna("total_s")[-60:]
    return a


def contagem_historico_por_dia(dias: int = 14) -> list[tuple[str, int, int]]:
    """[(dd/mm, sucessos, erros)] dos últimos `dias` dias, a partir do historico.csv."""
    contagem: dict[date, list[int]] = {}
    try:
        with open(config.ARQ_HISTORICO, newline="", encoding="utf-8-sig") as f:
            for linha in csv.DictReader(f, delimiter=";"):
                try:
                    dia = datetime.strptime((linha.get("data_hora") or "")[:10], "%d/%m/%Y").date()
                except ValueError:
                    continue
                par = contagem.setdefault(dia, [0, 0])
                par[0 if (linha.get("status") or "") == "SUCESSO" else 1] += 1
    except (OSError, csv.Error):
        return []
    hoje = date.today()
    saida = []
    for n in range(dias - 1, -1, -1):
        dia = date.fromordinal(hoje.toordinal() - n)
        s, e = contagem.get(dia, [0, 0])
        saida.append((dia.strftime("%d/%m"), s, e))
    return saida


# ---- Relatório HTML -----------------------------------------------------------------------

def _svg_barras(itens: list[tuple[str, float]], unidade: str, largura: int = 640) -> str:
    """Gráfico de barras horizontais em SVG (sem bibliotecas), para o relatório."""
    if not itens:
        return "<p class='vazio'>Sem dados.</p>"
    maior = max(v for _, v in itens) or 1
    altura_barra, espaco, margem = 22, 8, 230
    altura = len(itens) * (altura_barra + espaco) + 10
    partes = [f"<svg viewBox='0 0 {largura} {altura}' width='100%' role='img' "
              f"xmlns='http://www.w3.org/2000/svg' font-family='Segoe UI, Arial' font-size='12'>"]
    for i, (rotulo, valor) in enumerate(itens):
        y = 5 + i * (altura_barra + espaco)
        w = max(2, (largura - margem - 90) * valor / maior)
        partes.append(f"<text x='{margem - 8}' y='{y + 15}' text-anchor='end' fill='#334155'>{escape(rotulo)}</text>")
        partes.append(f"<rect x='{margem}' y='{y}' width='{w:.1f}' height='{altura_barra}' rx='4' fill='#2563eb'/>")
        partes.append(f"<text x='{margem + w + 6:.1f}' y='{y + 15}' fill='#0f172a'>{num_br(valor)} {escape(unidade)}</text>")
    partes.append("</svg>")
    return "".join(partes)


def _tabela(cabecalho: list[str], linhas: list[list[str]]) -> str:
    th = "".join(f"<th>{escape(c)}</th>" for c in cabecalho)
    corpo = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in linha) + "</tr>" for linha in linhas)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{corpo}</tbody></table>"


def gerar_relatorio_html(caminho: Path, diagnostico: list[ItemDiagnostico] | None = None,
                         benchmarks: list[ResultadoBenchmark] | None = None,
                         analise: AnaliseAutomacao | None = None) -> Path:
    """Relatório completo e autossuficiente (abre em qualquer navegador e pode ser impresso)."""
    from .motor import ROTULO_ETAPA

    analise = analise or analisar_automacao()
    secoes = []
    icone = {OK: "✔", AVISO: "⚠", ERRO: "✖", INFO: "•"}
    if diagnostico:
        linhas = [[escape(i.grupo), escape(i.nome), f"<span class='{i.status}'>{icone[i.status]}</span> "
                   f"{escape(i.valor)}", f"<small>{escape(i.detalhe)}</small>"] for i in diagnostico]
        secoes.append("<h2>1. Diagnóstico do sistema</h2>" + _tabela(["Grupo", "Item", "Resultado", "Detalhe"], linhas))
    if benchmarks:
        linhas = [[escape(b.nome), f"<b>{num_br(b.valor)}</b> {escape(b.unidade)}",
                   "maior é melhor" if b.maior_melhor else "menor é melhor", f"<small>{escape(b.detalhe)}</small>"]
                  for b in benchmarks]
        secoes.append("<h2>2. Testes de velocidade</h2>" + _tabela(["Teste", "Resultado", "Leitura", "Detalhe"], linhas))
    est = [["Lote completo", analise.total], ["Fase DARE (gerar + PDF)", analise.dare],
           ["Fase SEI (anexar)", analise.sei], ["Conexão com o navegador", analise.conexao]]
    linhas = [[n, str(e.n), num_br(e.media), num_br(e.mediana), num_br(e.desvio), num_br(e.minimo),
               num_br(e.maximo), num_br(e.p95), num_br(e.cv, 1) + " %"] for n, e in est if e.n]
    resumo = (f"<div class='kpis'><div><b>{analise.lotes}</b><span>lançamentos medidos</span></div>"
              f"<div><b>{num_br(analise.taxa_sucesso, 1)} %</b><span>taxa de sucesso</span></div>"
              f"<div><b>{num_br(analise.total.media, 1)} s</b><span>tempo médio por lote</span></div>"
              f"<div><b>{num_br(analise.lotes_por_hora, 0)}</b><span>lotes por hora (estimado)</span></div></div>")
    etapas = [(ROTULO_ETAPA[c], e.media) for c, e in analise.etapas.items()]
    gargalo = (f"<p><b>Gargalo:</b> {escape(ROTULO_ETAPA[analise.gargalo])} "
               f"({num_br(analise.etapas[analise.gargalo].media)} s em média, "
               f"{num_br(analise.etapas[analise.gargalo].media / analise.total.media * 100 if analise.total.media else 0, 1)} % do lote).</p>"
               if analise.gargalo else "")
    secoes.append(
        "<h2>3. Desempenho da automação (execuções reais)</h2>" + resumo
        + (_tabela(["Medida (segundos)", "n", "Média", "Mediana", "Desvio padrão", "Mín", "Máx", "P95", "CV"], linhas)
           if linhas else "<p class='vazio'>Ainda não há execuções medidas. Rode lançamentos pelo aplicativo.</p>")
        + "<h3>Tempo médio por etapa</h3>" + _svg_barras(etapas, "s") + gargalo
        + "<p class='nota'>Tempos medidos com relógio de alta resolução (perf_counter) a partir das mensagens "
          "de cada etapa. Estatísticas calculadas somente com lotes concluídos com sucesso. P95 = 95% dos lotes "
          "levaram até este tempo; CV = desvio padrão ÷ média (variabilidade).</p>"
    )
    html = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>Relatório de desempenho - DARE Automação</title>
<style>
body{{font-family:'Segoe UI',Arial,sans-serif;color:#0f172a;max-width:980px;margin:32px auto;padding:0 20px;line-height:1.5}}
h1{{font-size:26px;margin:0}} h2{{font-size:19px;margin-top:36px;border-bottom:2px solid #e2e8f0;padding-bottom:6px}}
h3{{font-size:15px;margin-top:22px}} .sub{{color:#475569;margin-top:4px}}
table{{border-collapse:collapse;width:100%;font-size:13px;margin-top:10px}}
th,td{{text-align:left;padding:7px 9px;border-bottom:1px solid #e2e8f0;vertical-align:top}}
th{{background:#f1f5f9;font-weight:600}} small{{color:#64748b}}
.ok{{color:#15803d}} .aviso{{color:#b45309}} .erro{{color:#b91c1c}} .info{{color:#64748b}}
.kpis{{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0}} .kpis div{{flex:1;min-width:150px;background:#f8fafc;
border:1px solid #e2e8f0;border-radius:10px;padding:12px}} .kpis b{{display:block;font-size:22px}}
.kpis span{{color:#475569;font-size:12px}} .nota{{color:#64748b;font-size:12px}} .vazio{{color:#64748b}}
@media print{{body{{margin:0}}}}
</style></head><body>
<h1>Relatório de desempenho</h1>
<p class="sub">DARE Automação v{__version__} · gerado em {datetime.now():%d/%m/%Y %H:%M} ·
computador {escape(platform.node())} · {escape(_nome_processador())}</p>
{''.join(secoes)}
</body></html>"""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(html, encoding="utf-8")
    return caminho
