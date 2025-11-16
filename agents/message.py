from spade.message import Message
import json

def make_message(to, performative, body_dict, protocol=None, language="json"):
    """Cria uma mensagem SPADE configurada com metadados e corpo JSON.
    
    Esta função auxiliar constrói uma mensagem SPADE padronizada com os
    metadados necessários (performative, language, protocol) e serializa
    o corpo da mensagem em formato JSON.
    
    Args:
        to (str): JID (Jabber ID) do destinatário da mensagem.
        performative (str): Tipo de performativa da mensagem (e.g., "inform",
            "request", "propose"). Define a intenção comunicativa da mensagem.
        body_dict (dict): Dicionário contendo os dados a enviar no corpo da
            mensagem. Será serializado para JSON.
        protocol (str, optional): Nome do protocolo de comunicação utilizado.
            Se None, o metadado de protocolo não é definido. Defaults to None.
        language (str, optional): Linguagem de serialização do corpo da mensagem.
            Defaults to "json".
    
    Returns:
        spade.message.Message: Mensagem SPADE configurada e pronta para envio,
            com metadados definidos e corpo serializado em JSON.
    
    Example:
        >>> msg = make_message(
        ...     to="agent@localhost",
        ...     performative="inform",
        ...     body_dict={"status": "ready", "value": 42},
        ...     protocol="negotiation"
        ... )
        >>> print(msg.body)
        '{"status": "ready", "value": 42}'
    """
    msg = Message(to=to)
    msg.set_metadata("performative", performative)
    msg.set_metadata("language", language)
    if protocol:
        msg.set_metadata("protocol", protocol)
    msg.body = json.dumps(body_dict)
    return msg