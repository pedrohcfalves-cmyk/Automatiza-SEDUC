"""
Quanto tempo leva fazer 1 item À MÃO, sem o aplicativo (em minutos).

É a base de comparação da tela "Estatísticas": o tempo economizado é
(itens feitos x estes minutos) menos o tempo que a automação levou.

Este arquivo é atualizado pelo próprio aplicativo, no botão
"Salvar estimativas" da tela Estatísticas -- mas também pode ser editado
à mão (só os números). Fica no código de propósito: vai junto com o
programa e entra no histórico do git.

Última alteração: valores iniciais do programa (21/10/2026)

Copyright (c) 2026 Pedro Henrique Carpina Farias Alves. Todos os direitos reservados. Ver LICENSE.
"""

ESTIMATIVAS_MINUTOS = {
    "CE": 3.0,  # CE — Despesa Certificada (por CE)
    "NL": 3.0,  # NL — Nota de Lançamento (por NL)
    "PP": 3.0,  # PP — Preparação de Pagamento (por PP)
    "OB": 4.0,  # OB — Ordem Bancária (por OB)
    "CONFERENCIA": 2.0,  # Conferência — dados do processo no SEI (por processo)
    "ANEXAR": 5.0,  # Anexar — baixar e colocar no SEI (por processo)
}
