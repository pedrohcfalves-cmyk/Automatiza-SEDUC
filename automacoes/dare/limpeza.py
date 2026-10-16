"""
Limpeza da pasta dos PDFs (DARE_PDFs): listar, escolher o que apagar e apagar com segurança.

  listar_pdfs()           -> os PDFs da pasta, com tamanho, data e se estão "protegidos"
  selecionar()            -> aplica o critério escolhido pelo usuário (todos / mais antigos / até uma data)
  apagar()                -> manda para a Lixeira do Windows (padrão) ou apaga de vez

Protegidos = PDFs de DAREs que foram GERADOS mas NÃO anexados no SEI (o lote falhou no SEI).
Eles ainda podem ser necessários, então ficam de fora da limpeza, a menos que o usuário
desmarque a proteção. A informação vem do histórico (dados/historico.csv).
"""

import csv
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config

log = logging.getLogger("dare.limpeza")


@dataclass
class ArquivoPdf:
    caminho: Path
    tamanho: int  # bytes
    modificado: datetime
    protegido: bool = False  # DARE gerado mas não anexado no SEI

    @property
    def nome(self) -> str:
        return self.caminho.name

    @property
    def idade_dias(self) -> int:
        return (datetime.now() - self.modificado).days


@dataclass
class ResultadoLimpeza:
    apagados: int = 0
    bytes_liberados: int = 0
    para_lixeira: bool = False
    falhas: list[tuple[str, str]] = field(default_factory=list)  # (arquivo, motivo)


def formatar_bytes(n: float) -> str:
    """1536 -> '1,5 KB' (padrão brasileiro, vírgula decimal)."""
    for unidade in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unidade == "GB":
            if unidade == "bytes":
                return f"{int(n)} bytes"
            return f"{n:.1f} {unidade}".replace(".", ",")
        n /= 1024
    return f"{n:.1f} TB".replace(".", ",")


def _chave(caminho: str | Path) -> str:
    """Caminho normalizado para comparar (o Windows não diferencia maiúsculas)."""
    return os.path.normcase(os.path.abspath(str(caminho)))


def pdfs_nao_anexados(arq_historico: Path | None = None) -> set[str]:
    """PDFs que o histórico registra como gerados num lote com ERRO (não anexados no SEI)."""
    arq = arq_historico or config.ARQ_HISTORICO
    resultado: set[str] = set()
    try:
        with open(arq, newline="", encoding="utf-8-sig") as f:
            for linha in csv.DictReader(f, delimiter=";"):
                pdf = (linha.get("pdf") or "").strip()
                if not pdf:
                    continue
                if (linha.get("status") or "").upper() == "SUCESSO":
                    resultado.discard(_chave(pdf))  # anexado numa nova tentativa
                else:
                    resultado.add(_chave(pdf))
    except FileNotFoundError:
        pass
    except (OSError, csv.Error) as exc:
        log.warning("Não consegui ler o histórico para proteger PDFs (%s).", exc)
    return resultado


def listar_pdfs(pasta: Path | None = None, protegidos: set[str] | None = None) -> list[ArquivoPdf]:
    """Os PDFs da pasta (mais recentes primeiro). Usa os.scandir: rápido mesmo com milhares."""
    pasta = Path(pasta or config.PASTA_PDF)
    protegidos = pdfs_nao_anexados() if protegidos is None else protegidos
    arquivos: list[ArquivoPdf] = []
    try:
        with os.scandir(pasta) as it:
            for entrada in it:
                if not entrada.is_file() or not entrada.name.lower().endswith(".pdf"):
                    continue
                try:
                    info = entrada.stat()
                except OSError:
                    continue
                arquivos.append(ArquivoPdf(
                    Path(entrada.path), info.st_size, datetime.fromtimestamp(info.st_mtime),
                    _chave(entrada.path) in protegidos,
                ))
    except FileNotFoundError:
        return []
    arquivos.sort(key=lambda a: a.modificado, reverse=True)
    return arquivos


def resumo(arquivos: list[ArquivoPdf]) -> dict:
    total = sum(a.tamanho for a in arquivos)
    return {
        "quantidade": len(arquivos),
        "bytes": total,
        "mais_antigo": min((a.modificado for a in arquivos), default=None),
        "mais_recente": max((a.modificado for a in arquivos), default=None),
        "protegidos": sum(a.protegido for a in arquivos),
    }


def tamanho_pasta(pasta: Path | None = None) -> tuple[int, int]:
    """(quantidade de PDFs, bytes) sem ler o histórico: leve, para a barra de status."""
    qtd = total = 0
    try:
        with os.scandir(Path(pasta or config.PASTA_PDF)) as it:
            for entrada in it:
                if entrada.is_file() and entrada.name.lower().endswith(".pdf"):
                    try:
                        total += entrada.stat().st_size
                        qtd += 1
                    except OSError:
                        continue
    except (FileNotFoundError, NotADirectoryError):
        pass
    return qtd, total


def selecionar(arquivos: list[ArquivoPdf], criterio: str, dias: int = 30,
               ate: date | None = None, proteger: bool = True) -> list[ArquivoPdf]:
    """
    criterio: 'todos' | 'mais_antigos' (mais de `dias` dias) | 'ate_data' (modificados até `ate`).
    Com proteger=True, os PDFs não anexados no SEI ficam de fora.
    """
    if criterio == "todos":
        escolhidos = list(arquivos)
    elif criterio == "mais_antigos":
        limite = datetime.now() - timedelta(days=max(0, int(dias)))
        escolhidos = [a for a in arquivos if a.modificado < limite]
    elif criterio == "ate_data":
        if ate is None:
            raise ValueError("Informe a data.")
        escolhidos = [a for a in arquivos if a.modificado.date() <= ate]
    else:
        raise ValueError(f"Critério desconhecido: {criterio}")
    return [a for a in escolhidos if not (proteger and a.protegido)]


# ---- Apagar -------------------------------------------------------------------------------

def _para_lixeira_windows(caminhos: list[Path]) -> None:
    """Manda vários arquivos para a Lixeira numa única operação do Windows (SHFileOperationW)."""
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", ctypes.c_void_p),
            ("pTo", ctypes.c_void_p),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE = 3
    FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 0x4, 0x10, 0x40, 0x400
    # Lista terminada por dois caracteres nulos, como a API exige.
    texto = "\0".join(str(Path(c).resolve()) for c in caminhos) + "\0\0"
    buffer = (ctypes.c_wchar * len(texto))(*texto)
    operacao = SHFILEOPSTRUCTW(
        hwnd=None, wFunc=FO_DELETE, pFrom=ctypes.cast(buffer, ctypes.c_void_p), pTo=None,
        fFlags=FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI,
    )
    codigo = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operacao))
    if codigo:
        log.warning("SHFileOperationW devolveu o código %s.", codigo)


def apagar(arquivos: list[ArquivoPdf], lixeira: bool = True) -> ResultadoLimpeza:
    """
    Apaga os arquivos. Com lixeira=True (e no Windows) eles vão para a Lixeira e podem ser
    recuperados; senão são apagados de vez. Conta o que realmente sumiu do disco.
    """
    resultado = ResultadoLimpeza(para_lixeira=lixeira and os.name == "nt")
    if not arquivos:
        return resultado
    if resultado.para_lixeira:
        try:
            for i in range(0, len(arquivos), 500):  # lotes de 500: a operação não fica enorme
                _para_lixeira_windows([a.caminho for a in arquivos[i:i + 500]])
        except Exception:  # noqa: BLE001 - sem Lixeira (ex.: pasta de rede): apaga de vez
            log.warning("Lixeira indisponível; os arquivos serão apagados de vez.", exc_info=True)
            resultado.para_lixeira = False
    for a in arquivos:
        if not resultado.para_lixeira:
            try:
                a.caminho.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                resultado.falhas.append((a.nome, str(exc)))
                continue
        if a.caminho.exists():
            if not any(nome == a.nome for nome, _ in resultado.falhas):
                resultado.falhas.append((a.nome, "o arquivo está aberto ou sem permissão"))
            continue
        resultado.apagados += 1
        resultado.bytes_liberados += a.tamanho
    log.info(
        "Limpeza: %d PDF(s) %s (%s); %d falha(s).", resultado.apagados,
        "enviados para a Lixeira" if resultado.para_lixeira else "apagados",
        formatar_bytes(resultado.bytes_liberados), len(resultado.falhas),
    )
    return resultado


def limpeza_automatica(dias: int, lixeira: bool = True, proteger: bool = True) -> ResultadoLimpeza:
    """Usada ao abrir o programa (se o usuário ativou): apaga os PDFs com mais de `dias` dias."""
    escolhidos = selecionar(listar_pdfs(), "mais_antigos", dias=dias, proteger=proteger)
    return apagar(escolhidos, lixeira=lixeira)
