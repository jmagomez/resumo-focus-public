"""A janela dos gráficos e a série que a meta contínua avalia.

Dois defeitos observados no painel publicado em 21/09/2026.

**A janela era contada em índice, não em calendário.** ``_secao_trajetoria``
recortava ``sorted({o.data for o in obs})[-52:]`` com o comentário de que eram
52 semanas. Só que a API de Expectativas entrega dado **diário**: o histórico
tinha 505 datas em dois anos, das quais 101 eram sextas-feiras. O corte rendia
``2026-07-08 → 2026-09-18`` — 72 dias corridos num gráfico rotulado como um
ano. O projeto baixava 730 dias de história (``--dias 730``) e desenhava 72.

O erro é silencioso por construção: o gráfico fica bonito, a linha existe, o
eixo tem datas. Nada falha. Só o período é outro.

**A série da meta contínua não era desenhada.** Desde janeiro de 2025 o CMN
avalia a meta mês a mês sobre o IPCA acumulado em doze meses. O terceiro
endpoint foi ligado justamente para trazer essa série, que estava no histórico
com 504 pontos e desvio-padrão — e o ``docs/index.html`` publicado tinha zero
ocorrências dela. Na edição de 18/09/2026 ela marcava **4,62%**, acima do teto
da banda (4,50%), e o painel não dizia.
"""

from datetime import date, timedelta

from focus import analytics as an
from focus import dashboard, store

BASE = date(2026, 9, 18)


def _serie_diaria(dias: int, *, referencia: str, horizonte: str = "anual", valor: float = 5.0):
    """Histórico em dias ÚTEIS, como a API entrega — não em sextas."""
    observacoes = []
    dia = BASE
    while len(observacoes) < dias:
        if dia.weekday() < 5:
            observacoes.append(
                store.Observacao(
                    data=dia.isoformat(),
                    indicador="IPCA",
                    horizonte=horizonte,
                    referencia=referencia,
                    base_calculo=0,
                    mediana=valor,
                    media=valor,
                    desvio_padrao=0.25,
                    n_respondentes=140,
                    fonte=store.FONTE_API,
                )
            )
        dia -= timedelta(days=1)
    return observacoes


# ── A janela ───────────────────────────────────────────────────────────


def test_o_historico_e_diario_e_nao_semanal():
    """A premissa que derrubava o recorte por índice."""
    obs = _serie_diaria(505, referencia="2027")
    datas = an.datas_disponiveis(obs)
    sextas = [d for d in datas if date.fromisoformat(d).weekday() == 4]

    assert len(datas) == 505
    assert len(sextas) == 101, "só uma em cada cinco datas é edição de sexta"


def test_recorte_por_indice_encolhe_a_janela_em_cinco_vezes():
    """O defeito, reproduzido: ``datas[-52:]`` não são 52 semanas."""
    obs = _serie_diaria(505, referencia="2027")
    datas = an.datas_disponiveis(obs)

    por_indice = date.fromisoformat(datas[-52:][0])
    assert (BASE - por_indice).days < 80, "o corte antigo cobria pouco mais de dez semanas"

    por_calendario = date.fromisoformat(an.desde_semanas(obs, 52))
    assert (BASE - por_calendario).days == 364, "a janela de calendário são 52 semanas cheias"


def test_janela_de_calendario_independe_da_frequencia_da_fonte():
    """Se o BCB dobrar a frequência, a janela não pode encolher junto."""
    esparso = _serie_diaria(60, referencia="2027")
    denso = _serie_diaria(505, referencia="2027")

    assert an.desde_semanas(esparso, 52) == an.desde_semanas(denso, 52)


def test_amostragem_semanal_deixa_a_sexta():
    """Uma marca por semana ISO, e que seja a edição — não a quarta-feira."""
    obs = _serie_diaria(505, referencia="2027")
    pontos = an.amostrar_semanal(an.trajetoria(obs, indicador="IPCA", referencia="2027"))

    assert 95 <= len(pontos) <= 105, "dois anos de história em ~100 marcas"
    dias = {date.fromisoformat(p.data).weekday() for p in pontos}
    assert dias == {4}, f"esperado só sexta-feira, veio {dias}"


def test_amostragem_semanal_preserva_ordem_e_ultimo_ponto():
    obs = _serie_diaria(30, referencia="2027")
    pontos = an.amostrar_semanal(an.trajetoria(obs, indicador="IPCA", referencia="2027"))

    assert [p.data for p in pontos] == sorted(p.data for p in pontos)
    assert pontos[-1].data == BASE.isoformat(), "o ponto mais recente não pode sumir"


# ── A série que a meta avalia ──────────────────────────────────────────


def _com_12_meses(valor: float):
    obs = _serie_diaria(60, referencia="2027")
    obs += [
        store.Observacao(
            data=o.data,
            indicador="IPCA",
            horizonte=an.HORIZONTE_12M,
            referencia=an.REFERENCIA_12M,
            base_calculo=0,
            mediana=valor,
            media=valor,
            desvio_padrao=0.4947,
            n_respondentes=135,
            fonte=store.FONTE_API,
        )
        for o in obs
    ]
    return obs


def test_expectativa_de_12_meses_acima_do_teto_e_acusada():
    """O caso real de 18/09/2026: 4,62% contra um teto de 4,50%."""
    leitura = an.expectativa_12_meses(_com_12_meses(4.6232), data=BASE.isoformat())

    assert leitura is not None
    assert not leitura.dentro_da_banda
    assert leitura.situacao == "acima do teto da banda"
    assert leitura.excesso == 0.1232
    assert leitura.desvio == 1.6232


def test_dentro_da_banda_nao_vira_alarme():
    leitura = an.expectativa_12_meses(_com_12_meses(3.9), data=BASE.isoformat())

    assert leitura is not None and leitura.dentro_da_banda
    assert leitura.situacao == "acima do centro"
    assert leitura.excesso == 0.0


def test_no_centro_da_meta():
    leitura = an.expectativa_12_meses(_com_12_meses(3.02), data=BASE.isoformat())
    assert leitura is not None and leitura.situacao == "no centro da meta"


def test_a_serie_de_12_meses_chega_ao_painel(tmp_path):
    """O defeito central: 504 pontos coletados, zero desenhados."""
    destino = tmp_path / "index.html"
    dashboard.construir(_com_12_meses(4.6232), destino=destino, hoje=BASE)
    pagina = destino.read_text(encoding="utf-8")

    assert "Meta contínua</h2>" in pagina, "a seção não foi montada"
    assert "g-meta-12m" in pagina, "o gráfico da série de 12 meses não foi desenhado"
    assert "acima do teto da banda" in pagina, "o painel tem de dizer que furou a banda"
    assert "4,62" in pagina


def test_painel_saudavel_nao_estampa_o_alerta_de_banda(tmp_path):
    destino = tmp_path / "index.html"
    dashboard.construir(_com_12_meses(3.4), destino=destino, hoje=BASE)
    pagina = destino.read_text(encoding="utf-8")

    assert "Meta contínua</h2>" in pagina
    # A classe existe sempre no CSS; o que não pode existir é a nota que a usa.
    assert 'class="nota alerta-texto"' not in pagina
    assert "teto da banda" not in pagina


def test_sem_a_serie_a_secao_some_em_vez_de_quebrar(tmp_path):
    """Histórico antigo, anterior ao terceiro endpoint, ainda gera painel."""
    destino = tmp_path / "index.html"
    dashboard.construir(_serie_diaria(60, referencia="2027"), destino=destino, hoje=BASE)
    pagina = destino.read_text(encoding="utf-8")

    assert "Meta contínua</h2>" not in pagina
    assert "Trajetória" in pagina, "o resto do painel continua de pé"


# ── A janela de dois anos, medida ────────────────────────────────────────


def test_janela_curta_apagaria_o_movimento_que_ja_aconteceu():
    """Por que a janela é de 104 semanas e não de 52.

    Nos dados reais, o IPCA de 2029 tem amplitude **0,00** na janela de um ano
    e 0,50 na de dois: ele se moveu antes, e desde então está parado. Em 52
    semanas sai como reta morta ocupando uma das quatro cores do gráfico. A
    janela curta não é mais legível — é mais pobre.

    Aqui isso é reproduzido: a série se move no primeiro ano e congela no
    segundo.
    """
    obs = []
    for o in _serie_diaria(520, referencia="2029"):
        idade = (BASE - date.fromisoformat(o.data)).days
        valor = 3.6 if idade <= 364 else 3.6 + (idade - 364) / 1000
        obs.append(
            store.Observacao(
                data=o.data,
                indicador="IPCA",
                horizonte="anual",
                referencia="2029",
                base_calculo=0,
                mediana=valor,
                media=valor,
                desvio_padrao=0.25,
                n_respondentes=140,
                fonte=store.FONTE_API,
            )
        )

    def amplitude(semanas):
        p = an.trajetoria(
            obs, indicador="IPCA", referencia="2029", desde=an.desde_semanas(obs, semanas)
        )
        return max(x.valor for x in p) - min(x.valor for x in p)

    assert amplitude(52) == 0.0, "em um ano a série é uma reta — nada a ler"
    assert amplitude(104) > 0.3, "em dois anos o movimento aparece"


def test_a_janela_do_painel_cobre_o_que_a_api_coleta():
    """104 semanas é exatamente o que `sincronizar` baixa: 730 dias."""
    from focus.dashboard import JANELA_SEMANAS

    assert JANELA_SEMANAS == 104
    assert JANELA_SEMANAS * 7 == 728, "dois anos, a mesma janela de --dias 730"


def test_a_serie_de_12_meses_cobre_dois_anos(tmp_path):
    """A leitura que a janela curta esconderia: a furada da banda é uma volta."""
    obs = _com_12_meses(4.6232)
    # Uma excursão acima do teto, bem no início da janela de dois anos.
    antiga = date(2025, 3, 7)
    obs += [
        store.Observacao(
            data=antiga.isoformat(),
            indicador="IPCA",
            horizonte=an.HORIZONTE_12M,
            referencia=an.REFERENCIA_12M,
            base_calculo=0,
            mediana=5.87,
            media=5.87,
            desvio_padrao=0.5,
            n_respondentes=130,
            fonte=store.FONTE_API,
        )
    ]

    de_dois_anos = an.serie_12_meses(obs, desde=an.desde_semanas(obs, 104))
    de_um_ano = an.serie_12_meses(obs, desde=an.desde_semanas(obs, 52))

    assert any(p.valor > 4.5 for p in de_dois_anos), "a excursão anterior tem de aparecer"
    assert not any(p.data == antiga.isoformat() for p in de_um_ano), (
        "em um ano ela fica de fora — e a furada de hoje pareceria a primeira"
    )
