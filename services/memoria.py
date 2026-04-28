from services.supabase_client import client

MAX_MENSAGENS = 20  # 10 pares usuário/agente


def carregar_historico() -> list[dict]:
    result = (
        client.table("historico_gestor")
        .select("role, content")
        .order("created_at", desc=True)
        .limit(MAX_MENSAGENS)
        .execute()
    )
    return list(reversed(result.data or []))


def salvar_historico(role: str, content: str):
    client.table("historico_gestor").insert({
        "role":    role,
        "content": content
    }).execute()
