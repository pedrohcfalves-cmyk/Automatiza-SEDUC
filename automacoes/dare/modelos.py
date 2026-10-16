"""Modelo dos dados digitados no menu."""

from dataclasses import dataclass
from datetime import date, datetime

from . import utils


@dataclass
class DadosDare:
    processo: str  # número do processo no SEI
    cnpj: str  # CNPJ usado para identificar o contribuinte no DARE
    cpf: str  # CPF do servidor
    cnpj_recolhedor: str
    mes_ano_referencia: str  # MMAAAA
    vencimento: date
    valor: str  # exibição: '100,00'
    origem: str = ""  # de onde veio, ex.: 'linha 7' (modo planilha); vazio no modo digitado

    @property
    def valor_digitos(self) -> str:
        """Valor em centavos, como o campo do site espera (100,00 -> '10000')."""
        return utils.valor_para_digitos(self.valor)

    def para_dict(self) -> dict:
        return {
            "processo": self.processo,
            "cnpj": self.cnpj,
            "cpf": self.cpf,
            "cnpj_recolhedor": self.cnpj_recolhedor,
            "mes_ano_referencia": self.mes_ano_referencia,
            "vencimento": self.vencimento.strftime("%d/%m/%Y"),
            "valor": self.valor,
            "origem": self.origem,
        }

    @classmethod
    def de_dict(cls, d: dict) -> "DadosDare | None":
        """Reconstrói os dados salvos; devolve None se o arquivo estiver incompleto."""
        try:
            return cls(
                processo=d["processo"],
                cnpj=d["cnpj"],
                cpf=d["cpf"],
                cnpj_recolhedor=d["cnpj_recolhedor"],
                mes_ano_referencia=d["mes_ano_referencia"],
                vencimento=datetime.strptime(d["vencimento"], "%d/%m/%Y").date(),
                valor=d["valor"],
                origem=str(d.get("origem") or ""),
            )
        except (KeyError, TypeError, ValueError):
            return None


@dataclass
class ResultadoLote:
    """Resultado do processamento de um lançamento."""

    dados: DadosDare
    sucesso: bool
    pdf: str = ""
    servidor: str = ""
    erro: str = ""
