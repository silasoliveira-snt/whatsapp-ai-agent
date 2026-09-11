import os
import time
import uuid
import logging
import requests
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

# 502/503/504 do gateway (AgileTalk) sao transitorios → vale re-tentar.
_RETRY_STATUS   = {502, 503, 504}
_MAX_TENTATIVAS = 3

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
    # payload montado uma vez: o externalKey unico serve de idempotencia no reenvio.
    payload = {
        "body":        body,
        "number":      number,
        "externalKey": str(uuid.uuid4()),
        "isClosed":    False
    }
    log.info(f"Enviando WhatsApp para {number} ({len(body)} chars)")

    for tentativa in range(1, _MAX_TENTATIVAS + 1):
        try:
            response = requests.post(BASE_URL, json=payload, headers=HEADERS, timeout=10)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if tentativa == _MAX_TENTATIVAS:
                raise
            log.warning(f"Envio para {number} falhou ({e}); retry {tentativa}/{_MAX_TENTATIVAS - 1} em {tentativa}s")
            time.sleep(tentativa)
            continue

        log.info(f"Status: {response.status_code}")
        # 502/503/504 sao transitorios no gateway → re-tenta (nunca re-tenta 2xx).
        if response.status_code in _RETRY_STATUS and tentativa < _MAX_TENTATIVAS:
            log.warning(f"Gateway {response.status_code} para {number}; retry {tentativa}/{_MAX_TENTATIVAS - 1} em {tentativa}s")
            time.sleep(tentativa)
            continue

        response.raise_for_status()  # 2xx retorna; 4xx/5xx (ou 502 na ultima) levanta
        return response.json()
