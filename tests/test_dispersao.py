"""Dispersão: o domínio do CV, a variação que faltava e o aviso que não limpava.

**O CV estava sendo aplicado fora do seu domínio.** A tabela "Dispersão entre
analistas" ordenava por coeficiente de variação — σ/μ — e as nove primeiras
linhas de dez eram "Resultado primário", cuja média ronda o zero:

    Resultado primário  2030   μ= 0,0556   σ=0,5705   CV= 1026,1%
    Resultado primário  2029   μ=-0,0748   σ=0,4396   CV=  587,7%

`IPCA 2030` caía para a **35ª posição de 75**. A tabela existe para mostrar
onde os analistas mais discordam e estava inteiramente ocupada por artefato de
divisão por quase-zero: não era discordância grande, era denominador pequeno.
Para variável que cruza o zero — resultado primário e nominal em % do PIB,
conta corrente em US$ bi — o CV não tem sequer sinal definido.

O ranking violava, de quebra, uma invariante escrita no CLAUDE.md do projeto:
*"Nunca misture unidades num mesmo eixo ou ranking"*. Misturava p.p., % do PIB,
R$/US$ e US$ bi.

**O texto prometia uma leitura que a tabela não entregava.** A nota dizia
"dispersão em alta com mediana estável indica distribuição se abrindo antes de
a mediana se mover" — mas a tabela era um retrato de uma data só. Não havia
nenhum Δ de dispersão no projeto inteiro.

**O `[aviso]` do vigia não podia ser resolvido.** As linhas sem dispersão eram
`Selic / mensal`, que a API de Expectativas não serve. O alerta aparecia em
toda execução e nunca limpava — a mesma patologia do falso positivo que o vigia
tinha no cálculo de atraso.
"""

from datetime import date, timedelta

import pytest
from conftest import fixture

from focus import analytics as an
from focus import api, store
from focus.cli import main

DATA = "2026-09-18"
QUATRO_SEMANAS_ANTES = "2026-08-21"


def _disp(indicador, referencia, *, media, desvio, desvio_4s=None):
    """Uma linha da tabela de dispersão, para testar as propriedades direto."""
    return an.Dispersao(
        indicador=indicador,
        referencia=referencia,
        media=media,
        desvio_padrao=desvio,
        minimo=media - 1,
        maximo=media + 1,
        n_respondentes=120,
        desvio_padrao_4s=desvio_4s,
    )


def _obs(indicador, referencia, *, media, desvio, data=DATA, horizonte="anual"):
    return store.Observacao(
        data=data,
        indicador=indicador,
        horizonte=horizonte,
        referencia=referencia,
        base_calculo=0,
        mediana=media,
        media=media,
        desvio_padrao=desvio,
        minimo=media - 1,
        maximo=media + 1,
        n_respondentes=120,
        fonte=store.FONTE_API,
    )


# ── O domínio do CV ─────────────────────────────────────────────────────


def test_media_perto_de_zero_nao_publica_cv():
    """O caso exato que dominava a tabela."""
    d = _disp("Resultado primário", "2030", media=0.0556, desvio=0.5705)

    assert d.desvio_padrao == 0.5705, "o desvio-padrão continua disponível"
    assert d.coeficiente_variacao is None, "σ/μ = 1026% não é discordância, é denominador"


def test_media_negativa_nao_publica_cv():
    """CV de variável que cruza o zero não tem sinal definido."""
    assert (
        _disp("Resultado primário", "2029", media=-0.0748, desvio=0.4396).coeficiente_variacao
        is None
    )
    assert (
        _disp("Resultado nominal", "2035", media=-6.4541, desvio=2.132).coeficiente_variacao is None
    )


def test_media_folgada_publica_cv_normalmente():
    """A correção não pode cegar o caso legítimo."""
    d = _disp("IPCA", "2030", media=4.30, desvio=0.5762)

    assert d.coeficiente_variacao == pytest.approx(0.134, abs=0.001)


@pytest.mark.parametrize(
    "media, desvio, publica",
    [
        (1.0, 0.49, True),  # razão 2,04 — passa raspando
        (1.0, 0.51, False),  # razão 1,96 — não passa
        (0.0, 0.30, False),  # zero exato
    ],
)
def test_o_limiar_e_o_declarado(media, desvio, publica):
    d = _disp("PIB", "2027", media=media, desvio=desvio)
    assert (d.coeficiente_variacao is not None) is publica
    assert an.RAZAO_MINIMA_PARA_CV == 2.0


def test_o_ipca_sobe_no_ranking_quando_o_ruido_sai():
    """O teste que nomeia o defeito: IPCA atrás de nove linhas de artefato."""
    observacoes = [
        _obs("Resultado primário", str(ano), media=0.05, desvio=0.57) for ano in range(2028, 2036)
    ]
    observacoes.append(_obs("IPCA", "2030", media=4.30, desvio=0.5762))

    itens = an.dispersao(observacoes, data=DATA)
    ranking = sorted(
        (d for d in itens if d.coeficiente_variacao is not None),
        key=lambda d: -(d.coeficiente_variacao or 0),
    )

    assert [d.indicador for d in ranking] == ["IPCA"], (
        "com o CV restrito ao seu domínio, sobra o indicador que o painel existe para mostrar"
    )


def test_a_unidade_viaja_junto_com_a_linha():
    """Sem a unidade na tabela, o desvio-padrão das linhas sem CV é ilegível."""
    assert _disp("Resultado primário", "2030", media=0.05, desvio=0.57).unidade == "p.p."
    assert _disp("Balança comercial", "2030", media=70.0, desvio=15.0).unidade == "US$ bi"
    assert _disp("Câmbio", "2030", media=5.4, desvio=0.3).unidade == "R$"


# ── A variação que faltava ──────────────────────────────────────────────


def test_variacao_do_desvio_em_quatro_semanas():
    """O número que torna verdadeira a frase que o painel já publicava."""
    observacoes = [
        _obs("IPCA", "2030", media=4.30, desvio=0.5762),
        _obs("IPCA", "2030", media=4.25, desvio=0.4500, data=QUATRO_SEMANAS_ANTES),
    ]

    (d,) = [x for x in an.dispersao(observacoes, data=DATA) if x.indicador == "IPCA"]
    assert d.variacao_desvio == pytest.approx(0.1262), "a distribuição se abriu"


def test_variacao_ausente_quando_nao_ha_com_o_que_comparar():
    observacoes = [_obs("IPCA", "2030", media=4.30, desvio=0.5762)]
    (d,) = an.dispersao(observacoes, data=DATA)

    assert d.variacao_desvio is None, "sem edição de quatro semanas atrás, não se inventa Δ"


def test_a_comparacao_tolera_escorregamento_de_feriado():
    """Mesma regra de casamento de data que as revisões usam."""
    quase = (date.fromisoformat(QUATRO_SEMANAS_ANTES) - timedelta(days=3)).isoformat()
    observacoes = [
        _obs("IPCA", "2030", media=4.30, desvio=0.5762),
        _obs("IPCA", "2030", media=4.25, desvio=0.4500, data=quase),
    ]

    (d,) = [x for x in an.dispersao(observacoes, data=DATA) if x.indicador == "IPCA"]
    assert d.variacao_desvio is not None


# ── O aviso que não limpava ─────────────────────────────────────────────


def _cenario(tmp_path, monkeypatch, extras=()):
    dados = tmp_path / "data"
    saida = tmp_path / "output" / "focus"
    dados.mkdir(parents=True)
    saida.mkdir(parents=True)
    (dados / "focus_2026-09-18.txt").write_text(
        fixture("focus_bloco_vazio.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (saida / "focus_2026-09-18.html").write_text("<html></html>", encoding="utf-8")

    observacoes = [
        _obs("IPCA", "2026", media=5.01, desvio=0.25, data="2026-09-11"),
        _obs("IPCA", "2026", media=4.90, desvio=0.25),
        # A Selic mensal só existe no PDF: a API não a serve.
        store.Observacao(
            data=DATA,
            indicador="Selic",
            horizonte="mensal",
            referencia="2026-11",
            base_calculo=0,
            mediana=13.63,
            media=None,
            desvio_padrao=None,
            fonte=store.FONTE_PDF,
        ),
        *extras,
    ]
    historico = tmp_path / "hist.csv"
    store.mesclar(observacoes, historico)
    monkeypatch.setattr("focus.cli.PASTA_DADOS", dados)
    monkeypatch.setattr("focus.cli.PASTA_SAIDA", saida)
    return historico


def test_selic_mensal_do_pdf_nao_gera_aviso(tmp_path, monkeypatch, capsys):
    """O aviso permanente: aparecia toda semana e não havia como resolvê-lo."""
    historico = _cenario(tmp_path, monkeypatch)

    codigo = main(["verificar", "--historico", str(historico), "--hoje", "2026-09-21"])
    texto = capsys.readouterr()

    assert codigo == 0
    assert "[aviso]" not in texto.out, f"aviso irresolúvel voltou:\n{texto.out}"
    assert ("Selic", "mensal") in api.SEM_COBERTURA_NA_API


def test_linha_do_pdf_fora_da_lista_continua_avisando(tmp_path, monkeypatch, capsys):
    """A tolerância não pode virar cegueira: IPCA anual do PDF é sintoma real."""
    orfa = store.Observacao(
        data=DATA,
        indicador="IPCA",
        horizonte="anual",
        referencia="2029",
        base_calculo=0,
        mediana=3.5,
        media=None,
        desvio_padrao=None,
        fonte=store.FONTE_PDF,
    )
    historico = _cenario(tmp_path, monkeypatch, extras=[orfa])

    codigo = main(["verificar", "--historico", str(historico), "--hoje", "2026-09-21"])
    texto = capsys.readouterr()

    assert codigo == 0, "é aviso, não falha"
    assert "[aviso]" in texto.out
    assert "IPCA/anual" in texto.out, "o aviso tem de nomear a chave inesperada"
    assert "Selic" not in texto.out, "a linha estrutural não entra na contagem"


# ── Uma definição só, e o limiar medido ────────────────────────────────────


def test_as_tres_copias_do_cv_viraram_uma():
    """Havia três: `api.Expectativa`, `analytics.revisoes` e `Dispersao`.

    Só uma ganhou a guarda quando o defeito foi corrigido. Cópia de fórmula é
    como defeito volta — basta alguém ler a errada. Este teste falha se alguma
    delas voltar a divergir.
    """
    sem_dominio = {"desvio_padrao": 0.5705, "media": 0.0556}  # resultado primário 2030
    com_dominio = {"desvio_padrao": 0.5762, "media": 4.30}  # IPCA 2030

    for caso, esperado_e_none in ((sem_dominio, True), (com_dominio, False)):
        da_api = api.Expectativa(
            indicador="X",
            detalhe=None,
            data=DATA,
            referencia="2030",
            base_calculo=0,
            mediana=caso["media"],
            media=caso["media"],
            desvio_padrao=caso["desvio_padrao"],
            minimo=None,
            maximo=None,
            n_respondentes=100,
            horizonte="anual",
        )
        da_dispersao = _disp("X", "2030", media=caso["media"], desvio=caso["desvio_padrao"])
        direto = api.coeficiente_variacao(caso["desvio_padrao"], caso["media"])

        assert (da_api.coeficiente_variacao is None) is esperado_e_none
        assert da_api.coeficiente_variacao == da_dispersao.coeficiente_variacao == direto


def test_revisao_nao_carrega_mais_a_formula_sem_guarda():
    """Campo morto com fórmula errada é armadilha armada para o próximo leitor."""
    observacoes = [
        _obs("Resultado primário", "2030", media=0.0556, desvio=0.5705),
        _obs("Resultado primário", "2030", media=0.06, desvio=0.57, data="2026-09-11"),
    ]
    (r,) = [x for x in an.revisoes(observacoes, data=DATA) if x.indicador == "Resultado primário"]

    assert r.coeficiente_variacao is None, "a revisão publicava CV de 1.026%"


def test_o_limiar_separa_o_que_tem_de_separar_no_historico_real():
    """Canário do limiar, medido contra os dois anos versionados em data/.

    A razão μ/σ separa os indicadores em dois grupos sem sobreposição: os que
    cruzam o zero chegam no máximo a 1,26 e os que nunca cruzam começam em
    2,93. Se esta separação deixar de valer, o limiar precisa ser remedido —
    e é este teste que avisa, não o painel publicando 1.026% de novo.
    """
    observacoes = [
        o
        for o in store.carregar(store.CAMINHO_PADRAO)
        if o.horizonte == "anual"
        and o.base_calculo == 0
        and o.referencia.isdigit()
        and o.media is not None
        and o.desvio_padrao
    ]
    if not observacoes:  # pragma: no cover - histórico ausente num checkout raso
        pytest.skip("histórico real não disponível")

    publica = {
        o.indicador for o in observacoes if api.coeficiente_variacao(o.desvio_padrao, o.media)
    }
    cruzam_o_zero = {"Resultado primário", "Resultado nominal", "Conta corrente"}

    assert not (publica & cruzam_o_zero), (
        f"indicadores de média que cruza o zero voltaram a publicar CV: {publica & cruzam_o_zero}"
    )
    for esperado in ("IPCA", "Selic", "Câmbio", "PIB"):
        assert esperado in publica, f"{esperado} deixou de publicar CV — limiar apertado demais"
