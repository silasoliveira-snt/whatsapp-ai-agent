import os
import logging
import httpx
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

# O postgrest-py cria a sessao httpx com http2=True (hardcoded). Com o httpcore atual,
# uma conexao HTTP/2 do pool que recebe GOAWAY do proxy do Supabase estoura
# 'ConnectionTerminated' na requisicao seguinte (trava o agente). Forcamos HTTP/1.1,
# que nao tem esse modo de falha. Se a estrutura interna do postgrest mudar, cai no
# fallback (http2=True) sem derrubar a app.
try:
    _pg  = client.postgrest
    _old = _pg.session
    _pg.session = httpx.Client(
        base_url=_old.base_url,
        headers=_old.headers,
        timeout=_old.timeout,
        follow_redirects=True,
    )
    _old.close()
except Exception as _e:
    log.warning(f"Nao foi possivel forcar HTTP/1.1 no cliente Supabase: {_e}")
