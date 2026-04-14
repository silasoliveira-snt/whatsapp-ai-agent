from datetime import date, timedelta, datetime, timezone
from services.supabase_client import client
from services.whatsapp import send_reminder, send_report


def check_and_send_reminders():
    """
    Roda todo dia às 09h.
    Busca inscritos cujo evento é daqui 14 dias e ainda não receberam lembrete.
    """
    target_date = (date.today() + timedelta(days=14)).isoformat()

    result = (
        client.table("reminders")
        .select("*")
        .eq("data_evento", target_date)
        .eq("status", "pending")
        .execute()
    )

    for reminder in result.data:
        try:
            send_reminder(
                telefone=reminder["telefone"],
                data=reminder["data_evento"],
                unidade=reminder["unidade"],
                local=reminder["local"]
            )
            client.table("reminders").update({
                "status": "sent",
                "sent_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", reminder["id"]).execute()

            print(f"[LEMBRETE] Enviado para {reminder['nome']} ({reminder['telefone']})")

        except Exception as e:
            print(f"[ERRO] Falha ao enviar lembrete para {reminder['nome']}: {e}")


def check_and_send_reports():
    """
    Roda todo dia às 09h05.
    Busca eventos daqui 7 dias e envia relatório de confirmados/recusados/sem resposta
    para o número do organizador (uma mensagem por evento).
    """
    target_date = (date.today() + timedelta(days=7)).isoformat()

    result = (
        client.table("reminders")
        .select("*")
        .eq("data_evento", target_date)
        .eq("report_sent", False)
        .execute()
    )

    if not result.data:
        return

    # Agrupa por evento (unidade + data)
    eventos = {}
    for reminder in result.data:
        chave = (reminder["unidade"], reminder["data_evento"])
        if chave not in eventos:
            eventos[chave] = {"confirmados": [], "recusados": [], "sem_resposta": [], "ids": []}

        if reminder["status"] == "confirmed":
            eventos[chave]["confirmados"].append(reminder["nome"])
        elif reminder["status"] == "declined":
            eventos[chave]["recusados"].append(reminder["nome"])
        else:
            eventos[chave]["sem_resposta"].append(reminder["nome"])

        eventos[chave]["ids"].append(reminder["id"])

    for (unidade, data), grupos in eventos.items():
        try:
            send_report(
                unidade=unidade,
                data=data,
                confirmados=grupos["confirmados"],
                recusados=grupos["recusados"],
                sem_resposta=grupos["sem_resposta"]
            )

            # Marca todos os registros do evento como report enviado
            for reminder_id in grupos["ids"]:
                client.table("reminders").update({
                    "report_sent": True
                }).eq("id", reminder_id).execute()

            print(f"[RELATORIO] Enviado para evento {unidade} em {data}")

        except Exception as e:
            print(f"[ERRO] Falha ao enviar relatório para {unidade} em {data}: {e}")
