def _is_expandido(f: dict) -> bool:
    """Campo 'expandido' por opção do Tally: a key traz o UUID da opção (com hífen).

    Ex.: 'question_1EdZeg_10c1993a-707e-4a52-8773-f981735e5c86' (expandido) vs.
    'question_K057Eg' (campo real). Só os expandidos têm '-' na key, então essa é
    a marca confiável — não depende do texto do label (que pode ter parênteses de
    instrução, ex.: 'Nome Completo (Digite seu nome)').
    """
    return "-" in f.get("key", "")


def achar(fields: list, keyword: str, exclude_parens: bool = False) -> str:
    """Busca campo pelo label no payload Tally. Resolve DROPDOWN por ID.

    exclude_parens=True ignora os campos expandidos por opção (checkbox), para que a
    busca por 'nome'/'email'/etc. não case com uma opção tipo 'São Paulo (Zona Sul)'.
    """
    for f in fields:
        if keyword.lower() not in f["label"].lower():
            continue
        if exclude_parens and _is_expandido(f):
            continue
        tipo  = f.get("type", "")
        valor = f.get("value")
        if tipo == "DROPDOWN" and isinstance(valor, list):
            selected = [o["text"] for o in f.get("options", []) if o["id"] in valor]
            return selected[0] if selected else ""
        if valor is None:
            return ""
        return str(valor).strip()
    return ""


def achar_checkboxes(fields: list, keyword: str) -> list[str]:
    """Retorna textos selecionados de campo CHECKBOXES, ignorando os expandidos por opção."""
    for f in fields:
        if keyword.lower() not in f["label"].lower():
            continue
        if _is_expandido(f):
            continue
        if f.get("type") == "CHECKBOXES" and isinstance(f.get("value"), list):
            return [o["text"].strip() for o in f.get("options", []) if o["id"] in f["value"]]
    return []
