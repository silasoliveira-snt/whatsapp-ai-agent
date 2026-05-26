import os
import logging
from datetime import date, datetime
from services.supabase_client import client
from services.whatsapp import _send
from services.constants import CONFIRM_SENT, CONFIRM_CONFIRMED, CONFIRM_DECLINED

log = logging.getLogger(__name__)

GRUPOS_ATIVACAO = [g.strip() for g in os.getenv("GRUPOS_ATIVACAO", "").split(",") if g.strip()]
MENSAGEM_ATIVACAO = os.getenv("MENSAGEM_ATIVACAO", "")


# --- helpers privados ---

def _fmt_data(data: str) -> str:
    try:
        return datetime.strptime(data, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return data


def _get_presenciais(data: str) -> list[str]:
    cron = (
        client.table("cronograma")
        .select("treinamento")
        .eq("data", data)
        .neq("tipo", "online")
        .execute()
    )
    return [r["treinamento"] for r in (cron.data or [])]


def _montar_mensagem_ativacao(r: dict) -> str:
    nome_tr  = r["treinamento"]
    data_fmt = _fmt_data(r.get("data") or "")
    link     = r.get("link_inscricao") or ""
    template = r.get("mensagem_customizada") or MENSAGEM_ATIVACAO or (
        f"Boa tarde, rede Onodera!\n"
        f"Passando para reforçar a participação no *{nome_tr}*!\n"
        f"Contamos com a presença de vocês!"
    )
    mensagem = template.replace("{treinamento}", nome_tr).replace("{data}", data_fmt)
    if link:
        mensagem += f"\n\nInscrições: {link}"
    return mensagem


# --- queries (usadas pelo agente) ---

def listar_treinamentos() -> str:
    hoje   = date.today().isoformat()
    result = (
        client.table("cronograma")
        .select("data, treinamento, tipo, publico")
        .gte("data", hoje)
        .order("data")
        .execute()
    )
    if not result.data:
        return "Nenhum treinamento agendado a partir de hoje."
    linhas = [
        f"{r['data']} — {r['treinamento']} ({r['tipo']}, {r['publico']})"
        for r in result.data
    ]
    return f"{len(result.data)} treinamento(s) agendado(s):\n\n" + "\n".join(linhas)


def buscar_inscritos(data: str) -> str:
    result = (
        client.table("treinamentos")
        .select("nome, unidade, treinamento")
        .eq("data_treinamento", data)
        .eq("arquivado", False)
        .execute()
    )
    todos = result.data or []
    if not todos:
        return f"Nenhum inscrito para {data}."

    vistos: set[tuple] = set()
    registros = []
    for r in todos:
        chave = (r["treinamento"], r["nome"])
        if chave not in vistos:
            vistos.add(chave)
            registros.append(r)

    grupos = {}
    for r in registros:
        grupos.setdefault(r["treinamento"], []).append(f"{r['unidade']} - {r['nome']}")

    linhas = [
        f"{tr}:\n" + "\n".join(f"  {p}" for p in pessoas)
        for tr, pessoas in grupos.items()
    ]
    total = sum(len(p) for p in grupos.values())
    return f"{total} inscrito(s) em {data}:\n\n" + "\n\n".join(linhas)


def buscar_medicos(data: str) -> str:
    result = (
        client.table("treinamentos")
        .select("nome, unidade, crm, treinamento")
        .eq("data_treinamento", data)
        .eq("arquivado", False)
        .execute()
    )
    todos = [r for r in (result.data or []) if r.get("crm")]
    vistos: dict[str, dict] = {}
    for r in todos:
        if r["crm"] not in vistos:
            vistos[r["crm"]] = r
    medicos = list(vistos.values())

    if not medicos:
        return f"Nenhum médico inscrito para {data}."
    linhas = [f"{r['unidade']}, {r['nome']}, CRM: {r['crm']}" for r in medicos]
    return f"{len(medicos)} médico(s) inscrito(s):\n" + "\n".join(linhas)


# --- ações ---

def preview_confirmacao(data: str) -> str:
    presenciais = _get_presenciais(data)
    if not presenciais:
        return f"Nenhum treinamento presencial em {data}."

    result = (
        client.table("treinamentos")
        .select("nome, unidade, telefone_responsavel")
        .eq("data_treinamento", data)
        .in_("treinamento", presenciais)
        .is_("confirmacao_status", "null")
        .eq("arquivado", False)
        .execute()
    )
    registros = result.data or []
    if not registros:
        return f"Nenhum inscrito pendente de confirmação para {data}."

    grupos, sem_telefone = {}, []
    vistos: set[tuple] = set()
    for r in registros:
        chave = (r.get("unidade") or "Sem unidade", r["nome"])
        if chave in vistos:
            continue
        vistos.add(chave)
        telefone = r.get("telefone_responsavel") or ""
        unidade  = chave[0]
        if not telefone:
            sem_telefone.append(f"{unidade} — {r['nome']}")
            continue
        grupos.setdefault(unidade, []).append(r["nome"])

    linhas = [f"Preview — confirmações a enviar em {_fmt_data(data)}\n"]
    for unidade, nomes in grupos.items():
        linhas.append(f"• {unidade} ({len(nomes)} pessoa(s)):")
        linhas += [f"    - {n}" for n in nomes]
    if sem_telefone:
        linhas.append(f"\nSem telefone cadastrado ({len(sem_telefone)}):")
        linhas += [f"  ○ {n}" for n in sem_telefone]
    linhas.append("\nPara enviar, responda: pode enviar")
    return "\n".join(linhas)


def confirmar_presenca(data: str) -> str:
    presenciais = _get_presenciais(data)
    if not presenciais:
        return f"Nenhum treinamento presencial em {data}."

    result = (
        client.table("treinamentos")
        .select("*")
        .eq("data_treinamento", data)
        .in_("treinamento", presenciais)
        .is_("confirmacao_status", "null")
        .eq("arquivado", False)
        .execute()
    )
    registros = result.data or []
    if not registros:
        return f"Nenhum inscrito pendente de confirmação para {data}."

    grupos, sem_telefone = {}, []
    nomes_vistos: set[tuple] = set()
    for r in registros:
        telefone = r.get("telefone_responsavel") or ""
        unidade  = r.get("unidade") or "Sem unidade"
        chave_display = (unidade, r["nome"])
        if not telefone:
            if chave_display not in nomes_vistos:
                nomes_vistos.add(chave_display)
                sem_telefone.append(r["nome"])
            continue
        chave = (unidade, telefone)
        grupos.setdefault(chave, {"nomes": [], "ids": []})
        grupos[chave]["ids"].append(r["id"])
        if chave_display not in nomes_vistos:
            nomes_vistos.add(chave_display)
            grupos[chave]["nomes"].append(r["nome"])

    data_fmt       = _fmt_data(data)
    enviados, erros = [], []

    for (unidade, telefone), dados in grupos.items():
        nomes_lista = "\n".join(f"• {n}" for n in dados["nomes"])
        mensagem = (
            f"Treinamento — {data_fmt}\n"
            f"Unidade: *{unidade}*\n\n"
            f"Os seguintes inscritos confirmarão presença?\n"
            f"{nomes_lista}\n\n"
            f"Responda *SIM* para confirmar ou *NÃO* para recusar."
        )
        try:
            _send(telefone, mensagem)
            for rid in dados["ids"]:
                client.table("treinamentos").update({
                    "confirmacao_status": CONFIRM_SENT
                }).eq("id", rid).execute()
            enviados.append(f"{unidade} ({len(dados['nomes'])} pessoa(s))")
            log.info(f"Confirmação enviada para {unidade} ({telefone})")
        except Exception as e:
            erros.append(f"{unidade}: {e}")
            log.error(f"Erro ao confirmar {unidade}: {e}")

    linhas = [f"Confirmações enviadas — {data_fmt}"]
    if enviados:
        linhas.append(f"\n{len(enviados)} unidade(s) notificadas:")
        linhas += [f"  ✓ {e}" for e in enviados]
    if sem_telefone:
        linhas.append(f"\n{len(sem_telefone)} inscrito(s) sem telefone na unidade:")
        linhas += [f"  ○ {n}" for n in sem_telefone]
    if erros:
        linhas.append(f"\nErros:")
        linhas += [f"  ✗ {e}" for e in erros]
    return "\n".join(linhas)


def relatorio_confirmacoes(data: str) -> str:
    result = (
        client.table("treinamentos")
        .select("nome, unidade, treinamento, confirmacao_status")
        .eq("data_treinamento", data)
        .in_("confirmacao_status", [CONFIRM_SENT, CONFIRM_CONFIRMED, CONFIRM_DECLINED])
        .execute()
    )
    registros = result.data or []
    if not registros:
        return f"Nenhuma confirmação enviada para {data}."

    confirmados = [r for r in registros if r["confirmacao_status"] == CONFIRM_CONFIRMED]
    recusados   = [r for r in registros if r["confirmacao_status"] == CONFIRM_DECLINED]
    pendentes   = [r for r in registros if r["confirmacao_status"] == CONFIRM_SENT]

    linhas = [f"Confirmações — {_fmt_data(data)}"]
    if confirmados:
        linhas.append(f"\n✓ Confirmados ({len(confirmados)}):")
        linhas += [f"  {r['unidade']} — {r['nome']}" for r in confirmados]
    if recusados:
        linhas.append(f"\n✗ Recusados ({len(recusados)}):")
        linhas += [f"  {r['unidade']} — {r['nome']}" for r in recusados]
    if pendentes:
        linhas.append(f"\n○ Sem resposta ({len(pendentes)}):")
        linhas += [f"  {r['unidade']} — {r['nome']}" for r in pendentes]
    return "\n".join(linhas)


def preview_ativacao(data: str) -> str:
    if not GRUPOS_ATIVACAO:
        return "GRUPOS_ATIVACAO não configurado no Railway."

    cron = (
        client.table("cronograma")
        .select("data, treinamento, link_inscricao, mensagem_customizada")
        .eq("data", data)
        .neq("tipo", "online")
        .execute()
    )
    if not cron.data:
        return f"Nenhum treinamento presencial em {data}."

    linhas = [f"Preview — ativação de {_fmt_data(data)}\n"]
    for r in cron.data:
        mensagem = _montar_mensagem_ativacao(r)
        linhas.append(f"• {r['treinamento']}")
        linhas.append(f"  Grupos: {len(GRUPOS_ATIVACAO)} grupo(s)")
        linhas.append(f"  Mensagem:\n{mensagem}\n")
    linhas.append("Para enviar, responda: pode enviar")
    return "\n".join(linhas)


def ativar_treinamento(data: str) -> str:
    if not GRUPOS_ATIVACAO:
        return "GRUPOS_ATIVACAO não configurado no Railway."

    cron = (
        client.table("cronograma")
        .select("data, treinamento, link_inscricao, mensagem_customizada")
        .eq("data", data)
        .neq("tipo", "online")
        .execute()
    )
    if not cron.data:
        return f"Nenhum treinamento presencial em {data}."

    enviados, erros = [], []
    for r in cron.data:
        mensagem = _montar_mensagem_ativacao(r)
        for grupo in GRUPOS_ATIVACAO:
            try:
                _send(grupo, mensagem)
                log.info(f"Ativação enviada para grupo {grupo}: {r['treinamento']}")
            except Exception as e:
                erros.append(f"{r['treinamento']} → {grupo}: {e}")
                log.error(f"Erro ao ativar {r['treinamento']} para {grupo}: {e}")
        enviados.append(r["treinamento"])

    linhas = [f"Ativação — {_fmt_data(data)}"]
    if enviados:
        linhas.append(f"\n{len(enviados)} treinamento(s) ativado(s) em {len(GRUPOS_ATIVACAO)} grupo(s):")
        linhas += [f"  ✓ {t}" for t in enviados]
    if erros:
        linhas.append(f"\nErros:")
        linhas += [f"  ✗ {e}" for e in erros]
    return "\n".join(linhas)
