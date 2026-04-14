import re
from flask import Flask, request, jsonify
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from services.supabase_client import client
from services.whatsapp import send_reminder
from jobs.scheduler import check_and_send_reminders, check_and_send_reports

app = Flask(__name__)

# Inicia o scheduler ao subir a aplicação
scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
scheduler.add_job(check_and_send_reminders, "cron", hour=9, minute=0)
scheduler.add_job(check_and_send_reports,   "cron", hour=9, minute=5)
scheduler.start()


def normalize_phone(telefone: str) -> str:
    """Remove tudo que não é dígito e garante o DDI 55."""
    digits = re.sub(r"\D", "", telefone)
    if not digits.startswith("55"):
        digits = "55" + digits
    return digits


@app.route("/webhook/form", methods=["POST"])
def receive_form():
    """Recebe nova inscrição enviada pelo Make.com."""
    data = request.json

    nome      = data.get("nome", "").strip()
    telefone  = normalize_phone(data.get("telefone", ""))
    data_ev   = data.get("data_evento", "").strip()   # formato esperado: YYYY-MM-DD
    unidade   = data.get("unidade", "").strip()
    local     = data.get("local", "").strip()

    if not all([nome, telefone, data_ev, unidade, local]):
        return jsonify({"error": "Campos obrigatórios ausentes"}), 400

    record = client.table("reminders").insert({
        "nome":        nome,
        "telefone":    telefone,
        "data_evento": data_ev,
        "unidade":     unidade,
        "local":       local,
        "status":      "pending"
    }).execute()

    reminder_id = record.data[0]["id"]
    print(f"[FORM] Inscrito salvo: {nome} | evento {data_ev} | id {reminder_id}")

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


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
