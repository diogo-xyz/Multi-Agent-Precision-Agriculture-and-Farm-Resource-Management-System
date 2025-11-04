from spade.message import Message
import json

def make_message(to, performative, body_dict, protocol=None, language="json"):
    msg = Message(to=to)
    msg.set_metadata("performative", performative)
    msg.set_metadata("language", language)
    if protocol:
        msg.set_metadata("protocol", protocol)
    msg.body = json.dumps(body_dict)
    return msg