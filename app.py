import os
import re
from flask import Flask, request, jsonify
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from services.supabase_client import client
from services.whatsapp import send_reminder
from jobs.scheduler import check_and_send_reports

app = Flask(__name__)

# Inicia o scheduler ao subir a aplicação
# Apenas o relatório é automático (3 dias antes do evento, todo dia às 09h)
scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
scheduler.add_job(check_and_send_reports, "cron", hour=9, minute=0)
scheduler.start()

LOCAL_EVENTO = os.getenv("LOCAL_EVENTO", "")


@app.route("/webhook/form", methods=["POST"])
def receive_form():
    """Recebe nova inscrição enviada pelo Power Automate."""
    data = request.json

    nome       = data.get("nome", "").strip()
    unidade    = data.get("unidade", "").strip()
    tel_pessoa = re.sub(r"\D", "", data.get("telefone", ""))  # telefone da pessoa inscrita (guardado, não usado no disparo)
    data_ev    = data.get("data_evento", "").strip()          # formato esperado: YYYY-MM-DD

    if not all([nome, unidade, data_ev]):
        return jsonify({"error": "Campos obrigatórios ausentes: nome, unidade, data_evento"}), 400

    # Busca o telefone do franqueado/gerente responsável pela unidade
    unidade_result = (
        client.table("unidades")
        .select("telefone_responsavel")
        .eq("nome", unidade)
        .limit(1)
        .execute()
    )

    if not unidade_result.data:
        return jsonify({"error": f"Unidade '{unidade}' não cadastrada na base"}), 404

    telefone_responsavel = unidade_result.data[0]["telefone_responsavel"]

    record = client.table("reminders").insert({
        "nome":              nome,
        "telefone":          telefone_responsavel,
        "telefone_inscrito": tel_pessoa,
        "data_evento":       data_ev,
        "unidade":           unidade,
        "local":             LOCAL_EVENTO,
        "status":            "pending"
    }).execute()

    reminder_id = record.data[0]["id"]
    print(f"[FORM] Inscrito salvo: {nome} | unidade {unidade} | responsável {telefone_responsavel} | evento {data_ev} | id {reminder_id}")

    return jsonify({"ok": True, "id": reminder_id}), 200


@app.route("/webhook/whatsapp", methods=["POST"])
def receive_reply():
    """Recebe todas as mensagens do segundo número via Agile Talk."""
    data = request.json

    # Ignora mensagens enviadas pelo próprio bot
    if data.get("method") == "message_sent_waba":
        return jsonify({"ok": True}), 200

    telefone = data.get("ticket", {}).get("contact", {}).get("number", "")
    mensagem = data.get("msg", {}).get("body", "").strip().upper()

    # Aceita variações: SIM, NÃO, NAO, NÃO, sim, não...
    if mensagem not in ("SIM", "NÃO", "NAO"):
        return jsonify({"ok": True}), 200

    status = "confirmed" if mensagem == "SIM" else "declined"

    # Busca o lembrete mais recente desse telefone com status "sent"
    result = (
        client.table("reminders")
        .select("id")
        .eq("telefone", telefone)
        .eq("status", "sent")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not result.data:
        return jsonify({"ok": True}), 200

    reminder_id = result.data[0]["id"]

    client.table("reminders").update({
        "status":     status,
        "replied_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", reminder_id).execute()

    print(f"[RESPOSTA] Telefone {telefone} respondeu {mensagem} → {status}")
    return jsonify({"ok": True}), 200


@app.route("/disparar", methods=["GET"])
def disparar():
    """Disparo manual: envia WhatsApp para todos os pendentes de uma data de evento."""
    data_ev = request.args.get("data_evento", "").strip()

    if not data_ev:
        return jsonify({"error": "Informe o parâmetro data_evento (ex: /disparar?data_evento=2026-05-10)"}), 400

    result = (
        client.table("reminders")
        .select("*")
        .eq("data_evento", data_ev)
        .eq("status", "pending")
        .execute()
    )

    if not result.data:
        return jsonify({"ok": True, "enviados": 0, "msg": "Nenhum inscrito pendente para essa data"}), 200

    enviados, erros = 0, []

    for reminder in result.data:
        try:
            send_reminder(
                telefone=reminder["telefone"],
                data=reminder["data_evento"],
                unidade=reminder["unidade"],
                local=reminder["local"]
            )
            client.table("reminders").update({
                "status":   "sent",
                "sent_at":  datetime.now(timezone.utc).isoformat()
            }).eq("id", reminder["id"]).execute()
            enviados += 1
            print(f"[DISPARO] Enviado para {reminder['nome']} ({reminder['telefone']})")
        except Exception as e:
            erros.append(reminder["nome"])
            print(f"[ERRO] Falha ao enviar para {reminder['nome']}: {e}")

    return jsonify({"ok": True, "enviados": enviados, "erros": erros}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
