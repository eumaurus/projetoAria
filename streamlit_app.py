"""Interface Streamlit do Projeto LUX."""

from __future__ import annotations
from datetime import datetime

from html import escape
from time import perf_counter

import pandas as pd
import streamlit as st

from app.container import construir_container, construir_controle_acesso


@st.cache_resource
def obter_container(versao: str = "governanca-v4"):
    """Monta o container; a versão invalida caches de versões antigas."""
    return construir_container()


@st.cache_resource
def obter_controle_acesso():
    """Carrega somente a validação de acesso para a tela de login."""
    return construir_controle_acesso()


EXEMPLOS = (
    "Quantos incidentes tivemos por prioridade?",
    "Qual a taxa média de KPI violado por grupo designado?",
    "Compare o volume real com a previsão D1 e D7.",
)


def aplicar_estilo() -> None:
    """Aplica uma identidade visual centrada na conversa."""
    st.markdown(
        """
        <style>
        :root { --ink:#10172a; --muted:#60708e; --brand:#5b5ce2; --line:#e7eaf2; }
        .stApp { background:#f7f8fc; color:var(--ink); }
        [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stLogo"] { display:none !important; }
        [data-testid="stMainBlockContainer"] { padding-top:1.25rem; }
        [data-testid="stSidebar"] { background:#10172a; border:0; }
        [data-testid="stSidebar"] * { color:#eef1ff; }
        [data-testid="stSidebar"] .stButton > button { background:transparent; border:1px solid rgba(255,255,255,.14); color:#e9edff; text-align:left; border-radius:10px; min-height:40px; padding:.45rem .65rem; }
        [data-testid="stSidebar"] .stButton > button:hover { background:rgba(255,255,255,.09); border-color:#8288ff; }
        .aira-wordmark { font-size:1.15rem; font-weight:800; letter-spacing:.12em; }
        .sidebar-label { color:#9ba8c8 !important; font-size:.73rem; letter-spacing:.10em; text-transform:uppercase; margin:1.5rem 0 .5rem; }
        .hero { padding:1.25rem 0 .85rem; }.eyebrow { color:var(--brand); font-size:.74rem; letter-spacing:.12em; font-weight:800; text-transform:uppercase; }
        .hero h1 { font-size:clamp(2rem,4vw,3.2rem); letter-spacing:-.055em; margin:.28rem 0 0; color:#11192d; }
        .hero p { color:var(--muted); font-size:1.04rem; max-width:620px; margin:.65rem 0 0; }
        .status-dot { display:inline-block; width:8px; height:8px; border-radius:50%; background:#20bd86; margin-right:7px; box-shadow:0 0 0 4px #dff7ed; }
        .welcome { background:linear-gradient(135deg,#5b5ce2,#7477f7); color:#fff; padding:1.3rem 1.45rem; border-radius:18px; margin:1.25rem 0 .75rem; box-shadow:0 13px 30px rgba(74,76,185,.18); }
        .welcome h3 { color:#fff; margin:0 0 .4rem; font-size:1.25rem; }.welcome p { color:#e9eaff; margin:0; }
        .feature { background:#fff; border:1px solid var(--line); border-radius:14px; padding:1rem 1.05rem; min-height:104px; }.feature b { display:block; color:#27324c; margin:.25rem 0; }.feature span { color:var(--muted); font-size:.88rem; }
        [data-testid="stChatMessage"] { background:transparent; padding:.7rem 0; } [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] { line-height:1.62; }
        .tag-row { display:flex; gap:.45rem; flex-wrap:wrap; margin:.5rem 0 .1rem; }.tag { font-size:.72rem; font-weight:700; padding:.22rem .56rem; border-radius:99px; background:#eef0ff; color:#4b4ecb; border:1px solid #dfe1ff; }.tag.aqua { background:#e2f8f5; color:#0d8478; border-color:#cdf0ec; }.tag.gold { background:#fff6dc; color:#9a6910; border-color:#faebc2; }
        .login-intro h1 { font-size:2rem; letter-spacing:-.045em; margin:0 0 .45rem; color:#11192d; }
        .login-intro p { color:var(--muted); margin:0 0 1.55rem; }
        .stTextInput input { border-radius:10px; border-color:#dce1ed; min-height:46px; }.stButton > button[kind="primary"] { border-radius:10px; background:#5b5ce2; border:0; font-weight:700; }.stButton > button[kind="primary"]:hover { background:#4648c7; }.stChatInput { border-radius:16px; border-color:#dce1ed; box-shadow:0 8px 24px rgba(26,36,70,.07); }.stExpander { border:1px solid var(--line); border-radius:11px; background:#fff; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def iniciar_estado() -> None:
    for chave, valor in {
        "autenticado": False, "email": "", "nivel": "", "historico": [],
        "pergunta_pendente": None, "historico_aberto": None, "pagina": "copiloto",
    }.items():
        st.session_state.setdefault(chave, valor)


def renderizar_login() -> None:
    _, centro, _ = st.columns((1, 2.2, 1))
    with centro:
        st.markdown(
            """
            <div class="login-intro">
                <h1>Bem-vindo ao AIRA</h1>
                <p>Seu copiloto para analisar incidentes, volumes operacionais e indicadores de KPI.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("login", clear_on_submit=False):
            email = st.text_input("E-mail corporativo", placeholder="voce@empresa.com")
            entrar = st.form_submit_button("Entrar no copiloto", type="primary", use_container_width=True)
        st.caption("O acesso é validado conforme as permissões da sua organização.")
    if entrar:
        try:
            with st.spinner("Validando acesso..."):
                controle_acesso = obter_controle_acesso()
            nivel = controle_acesso.validar(email)
            st.session_state.autenticado = True
            st.session_state.email = email.strip().lower()
            st.session_state.nivel = nivel.value
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def resumir(pergunta: str, limite: int = 38) -> str:
    return pergunta if len(pergunta) <= limite else f"{pergunta[:limite - 1].rstrip()}…"


def renderizar_lateral() -> None:
    with st.sidebar:
        st.markdown('<div class="aira-wordmark">☠︎︎ AIRA</div>', unsafe_allow_html=True)
        st.caption("OPERAÇÕES E KPI")
        st.divider()
        st.markdown(f"**{st.session_state.email}**")
        st.caption(f"Acesso nível {st.session_state.nivel}")
        if st.button("＋ Nova conversa", use_container_width=True):
            st.session_state.historico = []
            st.session_state.historico_aberto = None
            st.session_state.pagina = "copiloto"
            st.rerun()
        if st.session_state.nivel == "GOD":
            if st.session_state.pagina == "governanca":
                if st.button("← Início", use_container_width=True):
                    st.session_state.pagina = "copiloto"
                    st.rerun()
            elif st.button("▦ Governança & dados", use_container_width=True):
                st.session_state.pagina = "governanca"
                st.rerun()
        else:
            st.caption("Governança disponível para administradores.")
        st.markdown('<div class="sidebar-label">Histórico de perguntas</div>', unsafe_allow_html=True)
        historico = st.session_state.historico
        if not historico:
            st.caption("Suas perguntas aparecerão aqui.")
        for indice, item in enumerate(reversed(historico), start=1):
            posicao = len(historico) - indice
            if st.button(f"◦ {resumir(item['pergunta'])}", key=f"hist-{posicao}", use_container_width=True):
                st.session_state.historico_aberto = posicao
                st.rerun()
        st.markdown("<div style='height:2.5rem'></div>", unsafe_allow_html=True)
        if st.button("Sair", use_container_width=True):
            for chave in ("autenticado", "email", "nivel", "historico", "pergunta_pendente", "historico_aberto"):
                st.session_state.pop(chave, None)
            st.rerun()


def renderizar_resultado(item: dict, governanca_service) -> None:
    estado = item["estado"]
    with st.chat_message("user"):
        st.markdown(item["pergunta"])
    with st.chat_message("assistant", avatar="🤖"):
        if estado.get("erro"):
            st.error(estado["erro"])
        st.markdown(estado.get("resposta", "Não houve resposta para esta solicitação."))
        st.markdown("<div class='tag-row'>" f"<span class='tag'>{estado.get('intencao', 'ANÁLISE')}</span>" f"<span class='tag aqua'>{estado.get('agente', 'AIRA')}</span>" f"<span class='tag gold'>nível {estado.get('nivel', '-')}</span></div>", unsafe_allow_html=True)
        if estado.get("sql"):
            with st.expander("Ver consulta SQL"):
                st.code(estado["sql"], language="sql")
        if estado.get("contexto"):
            with st.expander("Ver contexto e métricas"):
                st.markdown(estado["contexto"])
        dados = estado.get("dados")
        if isinstance(dados, pd.DataFrame) and not dados.empty:
            with st.expander("Ver dados retornados"):
                st.dataframe(dados, use_container_width=True, hide_index=True)
        auditoria_id = item.get("auditoria_id")
        if auditoria_id:
            feedback = item.get("feedback")
            if feedback is None:
                positivo, negativo, _ = st.columns((1, 1, 5))
                if positivo.button("👍 Útil", key=f"positivo-{auditoria_id}"):
                    governanca_service.registrar_feedback(auditoria_id, 1)
                    item["feedback"] = 1
                    st.rerun()
                if negativo.button("👎 Melhorar", key=f"negativo-{auditoria_id}"):
                    governanca_service.registrar_feedback(auditoria_id, -1)
                    item["feedback"] = -1
                    st.rerun()
            else:
                st.caption("Feedback registrado: " + ("útil" if feedback == 1 else "precisa melhorar"))


def processar_pergunta(container, pergunta: str) -> None:
    inicio = perf_counter()
    with st.spinner("AIRA está analisando seus dados..."):
        estado = container.orquestrador.executar(pergunta, st.session_state.email)
    latencia_ms = round((perf_counter() - inicio) * 1000)
    auditoria_id = container.governanca_service.registrar_interacao(
        email=st.session_state.email,
        pergunta=pergunta,
        estado=estado,
        latencia_ms=latencia_ms,
    )
    st.session_state.historico.append(
        {
            "pergunta": pergunta,
            "estado": estado,
            "quando": datetime.now().isoformat(timespec="seconds"),
            "auditoria_id": auditoria_id,
        }
    )
    st.session_state.historico_aberto = None

def valor_indicador(valor, formato: str = "{:.0f}") -> str:
    """Formata lacunas de dados sem confundi-las com valor zero."""
    if valor is None or pd.isna(valor):
        return "—"
    return formato.format(valor)


def renderizar_indicador(titulo: str, valor: str, descricao: str) -> None:
    """Apresenta o indicador junto de sua definição operacional."""
    with st.container(border=True):
        st.metric(titulo, valor)
        st.caption(descricao)


def renderizar_nuvem_palavras(termos: list[tuple[str, int]]) -> None:
    """Cria nuvem de palavras nativa, sem enviar perguntas a serviços externos."""
    if not termos:
        st.info("A nuvem aparecerá depois que o AIRA receber perguntas registradas.")
        return
    maior = max(frequencia for _, frequencia in termos)
    cores = ("#5b5ce2", "#1c9d91", "#e39035", "#697795", "#a855f7")
    nuvem: list[str] = []
    for indice, (termo, frequencia) in enumerate(termos):
        tamanho = 15 + round(28 * frequencia / maior)
        nuvem.append(
            f"<span title='{frequencia} ocorrência(s)' style='font-size:{tamanho}px;color:{cores[indice % len(cores)]};'>"
            f"{escape(termo)}</span>"
        )
    st.markdown(
        "<div style='display:flex;gap:12px;align-items:center;justify-content:center;flex-wrap:wrap;"
        "padding:1.8rem 1rem;border:1px solid #e7eaf2;border-radius:16px;background:#fff;'>"
        + "".join(nuvem)
        + "</div>",
        unsafe_allow_html=True,
    )


def renderizar_governanca(container) -> None:
    """Painel administrativo de observabilidade, qualidade e auditoria."""
    if st.session_state.nivel != "GOD":
        st.error("Este painel é restrito a administradores.")
        return

    servico = container.governanca_service
    st.markdown("""<div class="hero"><div class="eyebrow">Governança, qualidade e sustentação</div>
    <h1>Visão operacional do AIRA</h1><p>Rastreie utilização, confiabilidade, custo estimado e sinais de qualidade do copiloto de incidentes em um único lugar.</p></div>""", unsafe_allow_html=True)
    if st.button("← Voltar ao copiloto"):
        st.session_state.pagina = "copiloto"
        st.rerun()

    periodo = st.selectbox("Período de análise", (7, 30, 90), index=1, format_func=lambda dias: f"Últimos {dias} dias")
    resumo = servico.resumo(periodo)
    linhas_a, linhas_b, linhas_c = st.columns(3), st.columns(3), st.columns(3)
    with linhas_a[0]:
        renderizar_indicador("Consultas", valor_indicador(resumo["consultas"]), "Volume de perguntas registradas no período; indica adoção e demanda pelo copiloto.")
    with linhas_a[1]:
        renderizar_indicador("Usuários ativos", valor_indicador(resumo["usuarios_ativos"]), "Quantidade de pessoas distintas que fizeram ao menos uma pergunta no período.")
    with linhas_a[2]:
        renderizar_indicador("Taxa de sucesso", valor_indicador(resumo["sucesso_pct"], "{:.1f}%"), "Percentual de interações concluídas sem erro registrado pelo orquestrador.")
    with linhas_b[0]:
        renderizar_indicador("Erros", valor_indicador(resumo["erros"]), "Falhas de processamento. Acompanhe este número para detectar regressões e indisponibilidades.")
    with linhas_b[1]:
        renderizar_indicador("Latência p95", valor_indicador(resumo["latencia_p95"], "{:.0f} ms"), "95% das respostas ficaram abaixo deste tempo; é mais útil que a média para perceber caudas lentas.")
    with linhas_b[2]:
        renderizar_indicador("Tokens estimados", valor_indicador(resumo["tokens_total"]), "Estimativa de entrada e saída pelo tamanho dos textos. Permite acompanhar consumo mesmo no modo mock.")
    with linhas_c[0]:
        renderizar_indicador("Tokens por consulta", valor_indicador(resumo["tokens_por_consulta"]), "Média estimada por pergunta; ajuda a detectar prompts, respostas ou contextos excessivamente longos.")
    with linhas_c[1]:
        renderizar_indicador("Feedback positivo", valor_indicador(resumo["feedback_positivo_pct"], "{:.1f}%"), "Percentual de avaliações positivas entre respostas avaliadas. É o sinal direto de utilidade percebida.")
    with linhas_c[2]:
        renderizar_indicador("Cobertura RAG", valor_indicador(resumo["cobertura_rag_pct"], "{:.1f}%"), "Percentual de perguntas RAG com contexto recuperado. Mede a disponibilidade prática do conhecimento indexado.")
    st.caption("Tokens são estimativas enquanto o provedor não expõe contagem de uso por chamada. Feedback positivo sem dados significa que ainda não há avaliações.")

    st.divider()
    esquerda, direita = st.columns((1.15, 1))
    with esquerda:
        st.subheader("Nuvem de intenções")
        st.caption("Termos mais frequentes nas perguntas, sem palavras funcionais. Use para priorizar cobertura de dados, melhorias de prompt e novos indicadores.")
        renderizar_nuvem_palavras(servico.frequencia_palavras(periodo))
    with direita:
        st.subheader("Uso por pessoa")
        st.caption("Volume, tokens estimados, latência média e sucesso por usuário autorizado.")
        usuarios = servico.resumo_por_usuario(periodo)
        st.dataframe(usuarios, use_container_width=True, hide_index=True, height=260)

    st.divider()
    st.subheader("Trilha de auditoria")
    st.caption("Cada linha registra quem perguntou, quando, o fluxo escolhido e os sinais necessários para investigação. A visualização é restrita ao nível GOD.")
    registros = servico.listar_interacoes(periodo)
    opcoes_usuarios = ["Todos"] + sorted(registros["email"].dropna().unique().tolist()) if not registros.empty else ["Todos"]
    usuario = st.selectbox("Filtrar por usuário", opcoes_usuarios)
    if usuario != "Todos":
        registros = registros[registros["email"] == usuario]
    if registros.empty:
        st.info("Ainda não há interações registradas para este recorte.")
    else:
        exibicao = registros[["criado_em", "email", "pergunta", "intencao", "agente", "status", "latencia_ms", "tokens_total", "contexto_disponivel", "feedback"]].copy()
        exibicao.columns = ["Data (UTC)", "Usuário", "Pergunta", "Intenção", "Agente", "Status", "Latência (ms)", "Tokens estimados", "Contexto", "Feedback"]
        exibicao["Contexto"] = exibicao["Contexto"].map({1: "sim", 0: "não"})
        exibicao["Feedback"] = exibicao["Feedback"].map({1: "positivo", -1: "negativo"}).fillna("não avaliado")
        st.dataframe(exibicao, use_container_width=True, hide_index=True, height=330)

    with st.expander("Como estes indicadores sustentam o projeto"):
        st.markdown(
            """
            - **Confiabilidade:** taxa de sucesso, erros e latência p95 mostram se o serviço opera dentro do esperado.
            - **Qualidade:** feedback do usuário e cobertura de contexto RAG ajudam a diferenciar uma resposta entregue de uma resposta útil.
            - **Custo e capacidade:** tokens estimados e utilização por pessoa revelam onde otimizar prompts, modelos e orçamento.
            - **Governança e evolução:** a trilha de auditoria permite investigar uma resposta específica, encontrar padrões de uso e priorizar melhorias.

            A separação entre sinais operacionais, dados, qualidade e uso segue a ideia de que sistemas de ML/IA precisam ser monitorados continuamente em produção, não apenas avaliados antes do lançamento.
            """
        )

def main():
    st.set_page_config(page_title="AIRA — Incidentes e KPI", page_icon="✦", layout="wide")
    aplicar_estilo()
    iniciar_estado()
    if not st.session_state.autenticado:
        renderizar_login()
        return
    container = obter_container()

    renderizar_lateral()
    if st.session_state.pagina == "governanca":
        renderizar_governanca(container)
        return

    st.markdown("""<div class="hero"><div class="eyebrow"><span class="status-dot"></span>Operação assistida por dados</div>
    <h1>O que você quer investigar?</h1><p>Converse com suas bases de incidentes e previsão para entender volume, SLA, KPI e tendência operacional.</p></div>""", unsafe_allow_html=True)
    historico = st.session_state.historico
    selecionado = st.session_state.historico_aberto
    if not historico:
        st.markdown("<div class='welcome'><h3>Comece por uma pergunta.</h3><p>O AIRA combina consultas, contexto das bases e análises de tendência operacional em uma única conversa.</p></div>", unsafe_allow_html=True)
        for coluna, icone, titulo, texto in zip(st.columns(3), ("⌕", "◈", "↗"), ("Consulte", "Entenda", "Analise"), ("Incidentes, prioridades, grupos, status e duração.", "Significado prático dos campos, métricas e flags das bases.", "Tendências de volume, previsões D1/D7 e comportamento de KPI."), strict=True):
            with coluna:
                st.markdown(f"<div class='feature'><span>{icone}</span><b>{titulo}</b><span>{texto}</span></div>", unsafe_allow_html=True)
        st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)
        for coluna, exemplo in zip(st.columns(3), EXEMPLOS, strict=True):
            with coluna:
                if st.button(exemplo, key=f"atalho-{exemplo}", use_container_width=True):
                    st.session_state.pergunta_pendente = exemplo
    elif selecionado is not None:
        st.caption("HISTÓRICO · CONSULTA SELECIONADA")
        renderizar_resultado(historico[selecionado], container.governanca_service)
        if st.button("Ver conversa completa"):
            st.session_state.historico_aberto = None
            st.rerun()
    else:
        for item in historico:
            renderizar_resultado(item, container.governanca_service)

    pergunta = st.chat_input("Pergunte sobre incidentes, prioridade, duração, grupos, previsão ou KPI...")
    pendente = st.session_state.pergunta_pendente
    if pendente:
        st.session_state.pergunta_pendente = None
        processar_pergunta(container, pendente)
        st.rerun()
    if pergunta:
        processar_pergunta(container, pergunta.strip())
        st.rerun()


if __name__ == "__main__":
   main()
