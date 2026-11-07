"""Alertas registradas en MongoDB; distribución externa por canal configurado."""
import ipaddress
import socket
import smtplib
from email.message import EmailMessage
from urllib.parse import urlparse
import httpx
from .crypto import decrypt_secret
from .db import db, audit, utcnow

def check_webhook_destination(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Se requiere un webhook HTTPS sin credenciales en la URL')
    # Protección inicial SSRF; para producción agregar proxy de salida y DNS pinning.
    for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM):
        address = ipaddress.ip_address(item[4][0])
        if not address.is_global:
            raise ValueError('El webhook no puede apuntar a redes privadas o locales')

def send_channel(channel, severity, message):
    if channel['kind'] == 'webhook':
        check_webhook_destination(channel['destination'])
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            response = client.post(channel['destination'], json={'text':f'[NORECOV] {severity.upper()}: {message}'})
            response.raise_for_status()
    else:
        email = EmailMessage()
        email['From'] = channel.get('smtp_username') or 'norecov@localhost'
        email['To'] = channel['destination']
        email['Subject'] = f'NORECOV - {severity.upper()}'
        email.set_content(message)
        with smtplib.SMTP(channel['smtp_host'], channel.get('smtp_port') or 587, timeout=10) as connection:
            connection.starttls()
            if channel.get('smtp_username'):
                connection.login(channel['smtp_username'], decrypt_secret(channel.get('secret_enc','')))
            connection.send_message(email)

def alert(severity, message, artifact_id=None):
    d = db()
    d.alertas.insert_one({'at':utcnow(),'severity':severity,'message':message,'artifact_id':artifact_id})
    for channel in d.canales_notificacion.find({'enabled':True,'severities':severity}):
        try:
            send_channel(channel, severity, message)
        except Exception as exc:
            audit('notification.failure', detail={'channel_id':str(channel['_id']),'error':str(exc)[:350]})
