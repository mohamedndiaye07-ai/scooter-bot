import os
import anthropic
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "mon_token_secret")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# Mémoire des clients : "actif", "non_interesse", "en_attente"
clients = {}

SYSTEM_PROMPT = """Tu es un agent commercial professionnel pour une entreprise qui vend des scooters électriques.

Informations produit :
- Vitesse maximale : 50 km/h
- Autonomie : 60 km
- Batterie : Plomb
- Fabriqué sur commande directement en Chine
- Délai de livraison : 45 à 90 jours selon conditions maritimes
- Paiement requis AVANT le lancement de la production
- Contact WhatsApp pour rendez-vous : 78 584 7485

Règles :
1. Sois toujours professionnel et courtois
2. Parle toujours au nom de l'entreprise (nous, notre équipe, nos agents)
3. Explique que le véhicule est fabriqué sur commande en Chine
4. Dis toujours "un de nos agents va prendre rendez-vous avec vous"
5. Si le client est prêt à acheter, invite-le à contacter le 78 584 7485 sur WhatsApp

IMPORTANT - Détection d'intérêt :
- Si le client montre clairement qu'il est intéressé par le scooter électrique → réponds normalement et termine ta réponse par exactement le mot [INTERESSE]
- Si le client montre clairement qu'il n'est PAS intéressé ou parle d'autre chose → réponds poliment que tu ne peux pas l'aider et termine par exactement le mot [NON_INTERESSE]
- Si ce n'est pas encore clair → pose des questions et termine par [EN_ATTENTE]"""

client_anthropic = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def send_message(recipient_id, text):
    url = "https://graph.facebook.com/v18.0/me/messages"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    requests.post(url, params=params, json=data)

def get_ai_response(user_message, history):
    messages = history + [{"role": "user", "content": user_message}]
    response = client_anthropic.messages.create(
        model="claude-opus-4-5",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=messages
    )
    return response.content[0].text

@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Token invalide", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                if "message" in event and not event["message"].get("is_echo"):
                    sender_id = event["sender"]["id"]
                    user_text = event["message"].get("text", "")
                    if not user_text:
                        continue

                    # Ignorer les clients non intéressés
                    if clients.get(sender_id, {}).get("statut") == "non_interesse":
                        continue

                    # Initialiser le client si nouveau
                    if sender_id not in clients:
                        clients[sender_id] = {"statut": "en_attente", "history": []}
                        send_message(sender_id, "Bonjour ! 👋 Bienvenue. Puis-je vous demander ce qui vous intéresse en particulier ?")
                        continue

                    # Obtenir la réponse IA
                    history = clients[sender_id]["history"]
                    response = get_ai_response(user_text, history)

                    # Détecter le statut
                    if "[INTERESSE]" in response:
                        clients[sender_id]["statut"] = "actif"
                        response = response.replace("[INTERESSE]", "").strip()
                    elif "[NON_INTERESSE]" in response:
                        clients[sender_id]["statut"] = "non_interesse"
                        response = response.replace("[NON_INTERESSE]", "").strip()
                    else:
                        response = response.replace("[EN_ATTENTE]", "").strip()

                    # Mettre à jour l'historique
                    clients[sender_id]["history"].append({"role": "user", "content": user_text})
                    clients[sender_id]["history"].append({"role": "assistant", "content": response})

                    send_message(sender_id, response)

    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
