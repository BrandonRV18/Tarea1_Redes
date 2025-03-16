#!/usr/bin/env python
from __future__ import print_function
import argparse
import csv
import io
from email.message import EmailMessage
from twisted.internet import reactor, protocol, defer
from twisted.application import internet, service
from twisted.mail import smtp, relaymanager
from email.utils import formatdate

class SMTPTutorialClient(smtp.ESMTPClient):
    def __init__(self, mailFrom, mailTo, mailData, *args, **kwargs):
        smtp.ESMTPClient.__init__(self, *args, **kwargs)
        self.mailFrom = mailFrom
        self.mailTo = mailTo
        self.mailData = mailData

    def getMailFrom(self):
        result = self.mailFrom
        return result

    def getMailTo(self):
        return [self.mailTo]

    def getMailData(self):
        msg = EmailMessage()
        msg.set_content(self.mailData, subtype='plain', charset='utf-8')

        msg['From'] = self.mailFrom
        msg['To'] = self.mailTo
        msg['Subject'] = "Invitación"
        msg['Date'] = formatdate(localtime=True)

        return io.BytesIO(msg.as_bytes())

    def sentMail(self, code, resp, numOk, addresses, log):
        print("Mensaje corrrectamente enviado a", self.mailTo)
        self.factory.deferred.callback(None)

class SMTPClientFactory(protocol.ClientFactory):
    def __init__(self, mailFrom, mailTo, mailData):
        self.mailFrom = mailFrom
        self.mailTo = mailTo
        self.mailData = mailData
        self.deferred = defer.Deferred()

    def buildProtocol(self, addr):
        p = SMTPTutorialClient(self.mailFrom, self.mailTo, self.mailData,
                                secret=None, identity='example.com')
        p.factory = self
        return p

    def clientConnectionFailed(self, connector, reason):
        print("Fallo en la conexión para", self.mailTo, ":", reason.getErrorMessage())
        self.deferred.errback(reason)

def main():
    parser = argparse.ArgumentParser(add_help=False, description="Cliente SMTP masivo y personalizado")
    parser.add_argument('-h', '--host', required=True, help='Servidor de correo')
    parser.add_argument('-c', '--csv', required=True, help='Archivo CSV con destinatarios')
    parser.add_argument('-m', '--message', required=True, help='Archivo con el mensaje a enviar (plantilla)')
    parser.add_argument('--help', action='help', default=argparse.SUPPRESS,
                        help='Mostrar este mensaje de ayuda y salir.')
    args = parser.parse_args()

    recipients = []
    with open(args.csv, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            recipients.append({'email': row['email'], 'name': row['name']})

    with open(args.message, 'r') as f:
        message_template = f.read()

    mailFrom = "brandonERV@brand0n.lat"
    deferreds = []

    for recipient in recipients:
        mailTo = recipient['email']
        mailData = message_template.format(name=recipient['name'])
        factory = SMTPClientFactory(mailFrom, mailTo, mailData)
        deferreds.append(factory.deferred)
        smtpService = internet.TCPClient(args.host, 2525, factory)
        smtpService.startService()

    for d in deferreds:
        d.addCallback(lambda envio: print("Envío exitoso para un destinatario"))
        d.addErrback(lambda err: print("Error en el envío:", err))

    dl = defer.DeferredList(deferreds, fireOnOneErrback=False, consumeErrors=True)
    dl.addBoth(lambda _: reactor.stop())
    reactor.run()

if __name__ == '__main__':
    main()
