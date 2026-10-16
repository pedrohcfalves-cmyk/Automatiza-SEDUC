"""
Licença de uso por chave de ativação.

Como funciona
-------------
* O programa mostra o CÓDIGO DESTA MÁQUINA (ex.: 7K2Q-9MXA-4TRB), derivado
  do identificador do Windows (MachineGuid). Não muda ao reiniciar nem ao
  reinstalar o programa.
* Quem administra as licenças gera, com o "Gerador de Licenças" (que NÃO vai
  no instalador), uma CHAVE para aquele código, com nome e validade.
* A chave é assinada com Ed25519. O programa leva só a CHAVE PÚBLICA, que
  confere a assinatura mas não consegue criar uma: sem a chave privada do
  administrador ninguém fabrica nem altera uma licença (mudar a validade ou o
  código invalida a assinatura).

Sem servidor, uma licença não pode ser cancelada à distância — o controle é
a VALIDADE. Para "cancelar", basta não renovar.

Formato da chave (uma linha; espaços e quebras de linha são ignorados):

    SIGEFSEI-<dados em base64url>.<assinatura em base64url>

Ed25519 em Python puro (RFC 8032, a implementação de referência), conferido
contra os vetores de teste oficiais da RFC — assim o programa não depende de
nenhuma biblioteca de criptografia extra.
"""
import base64
import hashlib
import json
import os
import uuid
from datetime import date

# Chave pública do emissor das licenças (par gerado pelo Gerador de Licenças).
CHAVE_PUBLICA_HEX = "5e44fadc0336bd2f76a2131fea5f5413e40836220207b6dad7aa2b156b545aca"

PREFIXO = "SIGEFSEI-"
PASTA_LICENCA = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                             "Automacao SIGEF-SEI")
ARQUIVO_LICENCA = os.path.join(PASTA_LICENCA, "licenca.txt")
ARQUIVO_USO = os.path.join(PASTA_LICENCA, "licenca_uso.json")
AVISO_VENCIMENTO_DIAS = 15


class ErroLicenca(Exception):
    pass


# ============================================================================
# Ed25519 (RFC 8032, seção 6 — implementação de referência)
# ============================================================================

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493


def _inv(x):
    return pow(x, _P - 2, _P)


_D = -121665 * _inv(121666) % _P
_RAIZ_MENOS_1 = pow(2, (_P - 1) // 4, _P)


def _soma(a, b):
    """Soma de pontos em coordenadas estendidas (X, Y, Z, T)."""
    x = (a[1] - a[0]) * (b[1] - b[0]) % _P
    y = (a[1] + a[0]) * (b[1] + b[0]) % _P
    z = 2 * a[3] * b[3] * _D % _P
    t = 2 * a[2] * b[2] % _P
    e, f, g, h = y - x, t - z, t + z, y + x
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _mult(n, ponto):
    resultado = (0, 1, 1, 0)
    while n > 0:
        if n & 1:
            resultado = _soma(resultado, ponto)
        ponto = _soma(ponto, ponto)
        n >>= 1
    return resultado


def _iguais(a, b):
    return ((a[0] * b[2] - b[0] * a[2]) % _P == 0
            and (a[1] * b[2] - b[1] * a[2]) % _P == 0)


def _recuperar_x(y, sinal):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1) % _P
    if x2 == 0:
        return None if sinal else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _RAIZ_MENOS_1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sinal:
        x = _P - x
    return x


_GY = 4 * _inv(5) % _P
_GX = _recuperar_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _comprimir(ponto):
    zinv = _inv(ponto[2])
    x = ponto[0] * zinv % _P
    y = ponto[1] * zinv % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _descomprimir(dados):
    if len(dados) != 32:
        return None
    y = int.from_bytes(dados, "little")
    sinal = y >> 255
    y &= (1 << 255) - 1
    x = _recuperar_x(y, sinal)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _hash_mod_l(dados):
    return int.from_bytes(hashlib.sha512(dados).digest(), "little") % _L


def _expandir(secreta):
    if len(secreta) != 32:
        raise ValueError("chave privada Ed25519 tem 32 bytes")
    h = hashlib.sha512(secreta).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def chave_publica_de(secreta):
    a, _prefixo = _expandir(secreta)
    return _comprimir(_mult(a, _G))


def assinar(secreta, mensagem):
    a, prefixo = _expandir(secreta)
    publica = _comprimir(_mult(a, _G))
    r = _hash_mod_l(prefixo + mensagem)
    r_comp = _comprimir(_mult(r, _G))
    h = _hash_mod_l(r_comp + publica + mensagem)
    s = (r + h * a) % _L
    return r_comp + int.to_bytes(s, 32, "little")


def verificar_assinatura(publica, mensagem, assinatura):
    if len(publica) != 32 or len(assinatura) != 64:
        return False
    ponto_a = _descomprimir(publica)
    ponto_r = _descomprimir(assinatura[:32])
    if ponto_a is None or ponto_r is None:
        return False
    s = int.from_bytes(assinatura[32:], "little")
    if s >= _L:
        return False
    h = _hash_mod_l(assinatura[:32] + publica + mensagem)
    return _iguais(_mult(s, _G), _soma(ponto_r, _mult(h, ponto_a)))


# ============================================================================
# Código da máquina e chave de licença
# ============================================================================

def _guid_do_windows():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as chave:
            return str(winreg.QueryValueEx(chave, "MachineGuid")[0])
    except Exception:
        return f"mac-{uuid.getnode():012x}"


def codigo_da_maquina():
    """12 caracteres em 3 grupos (ex.: 7K2Q-9MXA-4TRB). Estável neste Windows."""
    resumo = hashlib.sha256(f"SIGEFSEI|{_guid_do_windows()}".encode()).digest()
    texto = base64.b32encode(resumo).decode().replace("=", "")[:12]
    return f"{texto[:4]}-{texto[4:8]}-{texto[8:12]}"


def _b64(dados):
    return base64.urlsafe_b64encode(dados).decode().rstrip("=")


def _de_b64(texto):
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def montar_chave(secreta, nome, codigo_maquina, validade, identificador):
    """Usado só pelo Gerador de Licenças (precisa da chave privada)."""
    dados = {
        "id": identificador,
        "nome": nome.strip(),
        "maquina": codigo_maquina.strip().upper(),
        "validade": validade.isoformat(),
        "emitida": date.today().isoformat(),
    }
    corpo = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"{PREFIXO}{_b64(corpo)}.{_b64(assinar(secreta, corpo))}"


def ler_chave(texto, codigo_maquina=None, hoje=None):
    """Confere a chave e devolve os dados dela. Levanta ErroLicenca com o motivo."""
    if CHAVE_PUBLICA_HEX == "COLOCAR_AQUI":
        raise ErroLicenca("programa sem chave pública de licença configurada")
    texto = "".join((texto or "").split())
    if not texto.startswith(PREFIXO) or "." not in texto:
        raise ErroLicenca("isso não é uma chave de licença deste programa")
    corpo_b64, assinatura_b64 = texto[len(PREFIXO):].split(".", 1)
    try:
        corpo = _de_b64(corpo_b64)
        assinatura = _de_b64(assinatura_b64)
    except Exception:
        raise ErroLicenca("chave incompleta ou com caracteres trocados")
    if not verificar_assinatura(bytes.fromhex(CHAVE_PUBLICA_HEX), corpo, assinatura):
        raise ErroLicenca("chave inválida: não foi emitida para este programa ou foi alterada")
    dados = json.loads(corpo.decode("utf-8"))

    codigo_maquina = codigo_maquina or codigo_da_maquina()
    if dados.get("maquina") != codigo_maquina:
        raise ErroLicenca(f"esta chave é de outro computador ({dados.get('maquina')}); "
                          f"o código deste é {codigo_maquina}")
    validade = date.fromisoformat(dados["validade"])
    hoje = hoje or date.today()
    if hoje > validade:
        raise ErroLicenca(f"licença vencida em {validade:%d/%m/%Y}")
    dados["validade_data"] = validade
    dados["dias_restantes"] = (validade - hoje).days
    return dados


# ============================================================================
# Estado neste computador
# ============================================================================

def _ultimo_uso():
    try:
        with open(ARQUIVO_USO, encoding="utf-8") as arq:
            return date.fromisoformat(json.load(arq)["ultimo"])
    except Exception:
        return None


def _registrar_uso(hoje):
    try:
        os.makedirs(PASTA_LICENCA, exist_ok=True)
        anterior = _ultimo_uso()
        if anterior is None or hoje > anterior:
            with open(ARQUIVO_USO, "w", encoding="utf-8") as arq:
                json.dump({"ultimo": hoje.isoformat()}, arq)
    except OSError:
        pass


def estado():
    """
    {'valida', 'motivo', 'nome', 'validade', 'dias_restantes', 'aviso', 'codigo'}
    """
    codigo = codigo_da_maquina()
    resultado = {"valida": False, "motivo": "", "nome": "", "validade": "",
                 "dias_restantes": None, "aviso": "", "codigo": codigo}
    try:
        with open(ARQUIVO_LICENCA, encoding="utf-8") as arq:
            texto = arq.read()
    except OSError:
        resultado["motivo"] = "programa ainda não ativado neste computador"
        return resultado

    hoje = date.today()
    ultimo = _ultimo_uso()
    # Relógio voltado para trás (para esticar uma licença vencida): 1 dia de
    # folga para fuso/horário de verão.
    if ultimo is not None and (ultimo - hoje).days > 1:
        resultado["motivo"] = (f"a data deste computador ({hoje:%d/%m/%Y}) está antes do "
                               f"último uso ({ultimo:%d/%m/%Y}); acerte o relógio")
        return resultado
    try:
        dados = ler_chave(texto, codigo, hoje)
    except ErroLicenca as erro:
        resultado["motivo"] = str(erro)
        return resultado

    _registrar_uso(hoje)
    resultado.update(valida=True, nome=dados.get("nome", ""),
                     validade=f"{dados['validade_data']:%d/%m/%Y}",
                     dias_restantes=dados["dias_restantes"])
    if dados["dias_restantes"] <= AVISO_VENCIMENTO_DIAS:
        resultado["aviso"] = (f"A licença vence em {resultado['validade']} "
                              f"({dados['dias_restantes']} dia(s)). Peça a renovação.")
    return resultado


def ativar(texto):
    """Confere e grava a chave. Devolve estado() ou levanta ErroLicenca."""
    ler_chave(texto)
    os.makedirs(PASTA_LICENCA, exist_ok=True)
    with open(ARQUIVO_LICENCA, "w", encoding="utf-8") as arq:
        arq.write("".join(texto.split()))
    situacao = estado()
    if not situacao["valida"]:
        raise ErroLicenca(situacao["motivo"])
    return situacao


if __name__ == "__main__":
    print("Código desta máquina:", codigo_da_maquina())
    print(estado())
