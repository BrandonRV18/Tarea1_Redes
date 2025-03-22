from __future__ import print_function
import argparse
import csv
import io
from email.message import EmailMessage
from twisted.internet import reactor, protocol, defer
from twisted.application import internet, service
from twisted.mail import smtp, relaymanager
from email.utils import formatdate


class SMTPClient(smtp.ESMTPClient):
    def __init__(self, mailFrom, mailTo, mailData, *args, **kwargs):
        """
        Implementa un cliente SMTP para enviar correos.
        Entradas: mailFrom (Remitente), mailTo (Destinatario), mailData (COntenido del mensaje), *args, **kwargs
        Salidas: Ninguna
        """
        smtp.ESMTPClient.__init__(self, *args, **kwargs)
        self.mailFrom = mailFrom
        self.mailTo = mailTo
        self.mailData = mailData

    def getMailFrom(self):
        """
        Retorna la dirección de correo del remitente.
        Entradas: Ninguna
        Salidas: Dirección del remitente
        """
        result = self.mailFrom
        return result

    def getMailTo(self):
        """
        Retorna una lista con las direcciones de los destinatarios.
        Entradas: Ninguna
        Salidas: lista con las direcciones de los destinatarios.
        """
        return [self.mailTo]

    def getMailData(self):
        """
        Retorna el contenido del mensaje de correo en un objeto similar a un archivo.
        Entradas: Ninguna
        Salidas: Mensaje completo en formato bytes
        """
        msg = EmailMessage()
        msg.set_content(self.mailData, subtype='plain', charset='utf-8')
        msg['From'] = self.mailFrom
        msg['To'] = self.mailTo
        msg['Subject'] = "Invitación"
        msg['Date'] = formatdate(localtime=True)
        return io.BytesIO(msg.as_bytes())

    def sentMail(self, code, resp, numOk, addresses, log):
        """
        Se encarga de indicar que el mensaje ha sido enviado exitosamente.
        Entradas: code, resp, numOk, addresses, log
        Salidas: Ninguna (solamente notifica el callback del Deferred de la factoría)
        """
        self.factory.deferred.callback(None)

class SMTPClientFactory(protocol.ClientFactory):
    def __init__(self, mailFrom, mailTo, mailData):
        """
        Inicializa el factory con los datos del correo a enviar.
        Entradas: mailFrom, mailTo, mailData
        Salidas: Ninguna
        """
        self.mailFrom = mailFrom
        self.mailTo = mailTo
        self.mailData = mailData
        self.deferred = defer.Deferred()

    def buildProtocol(self, addr):
        """
        Crea y retorna una instancia de SMTPClient para la conexión entrante.
        Entradas: addr (dirección del servidor)
        Salidas: una instancia de SMTPClient
        """
        p = SMTPClient(self.mailFrom, self.mailTo, self.mailData,
                       secret=None, identity='Identity')
        p.factory = self
        return p

    def clientConnectionFailed(self, connector, reason):
        """
        Se encarga de indicar cuando la conexión con el servidor falla. Imprime el error y notifica el Deferred.
        Entradas: connector, reason (razón del fallo)
        Salidas: Ninguna
        """
        print("Fallo en la conexión para", self.mailTo, ":", reason.getErrorMessage())
        self.deferred.errback(reason)


def main():
    """
    Configura y envía los correos utilizando el cliente SMTP. Lee destinatarios desde un CSV y un TXT con el mensaje.
    Entradas: Ninguna
    Salidas: Inicia el envío de correos y detiene el reactor cuando termina
    """
    parser = argparse.ArgumentParser(add_help=False, description="Cliente SMTP masivo y personalizado")
    parser.add_argument('-h', '--host', required=True, help='Servidor de correo')
    parser.add_argument('-c', '--csv', required=True, help='Archivo CSV con destinatarios')
    parser.add_argument('-m', '--message', required=True, help='Archivo con el mensaje a enviar (plantilla)')
    parser.add_argument('--help', action='help', default=argparse.SUPPRESS,
                        help='Mostrar este mensaje de ayuda y salir.')
    args = parser.parse_args()

    # Guarda los destinatarios desde el CSV
    recipients = []
    with open(args.csv, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            recipients.append({'email': row['email'], 'name': row['name']})

    # Leer la plantilla del mensaje desde el archivo indicado
    with open(args.message, 'r') as f:
        message_template = f.read()

    #Remitente fijo
    mailFrom = "brandonERV@brand0n.lat"
    deferreds = []

    # Enviar un correo a cada destinatario
    for recipient in recipients:
        mailTo = recipient['email']
        mailData = message_template.format(name=recipient['name'])
        factory = SMTPClientFactory(mailFrom, mailTo, mailData)
        deferreds.append(factory.deferred)
        smtpService = internet.TCPClient(args.host, 2500, factory)
        smtpService.startService()

    # Agregar callbacks para cada Deferred del envío
    for d in deferreds:
        d.addCallback(lambda envio: print("Envío exitoso para un destinatario"))
        d.addErrback(lambda err: print("Error en el envío:", err))

    # Espera a que se completen todos los Deferred y detiene el reactor
    dl = defer.DeferredList(deferreds, fireOnOneErrback=False, consumeErrors=True)
    dl.addBoth(lambda _: reactor.stop())
    reactor.run()


if __name__ == '__main__':
    main()
