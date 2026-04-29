import os
import uuid
import logging
import requests
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

BASE_URL  = f"https://onochatapi.agiletalk.com.br/v2/api/external/{os.getenv('AGILE_CLIENT_PATH')}"
HEADERS   = {
    "Authorization": f"Bearer {os.getenv('AGILE_BEARERTOKEN')}",
    "Content-Type": "application/json"
}

GESTOR_NUMBER      = os.getenv("GESTOR_NUMBER")
AGENTE_AUTORIZADOS = set(
    n.strip() for n in os.getenv("AGENTE_NUMEROS_AUTORIZADOS", "").split(",") if n.strip()
)


def _send(number: str, body: str):
    payload = {
        "body":        body,
        "number":      number,
        "externalKey": str(uuid.uuid4()),
        "isClosed":    False
    }
    log.info(f"Enviando WhatsApp para {number} ({len(body)} chars)")
    response = requests.post(BASE_URL, json=payload, headers=HEADERS, timeout=10)
    log.info(f"Status: {response.status_code}")
    response.raise_for_status()
    return response.json()
