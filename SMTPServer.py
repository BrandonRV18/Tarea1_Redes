#!/usr/bin/env python3
import argparse
from twisted.application import internet, service
from twisted.cred.portal import Portal
from twisted.cred.checkers import InMemoryUsernamePasswordDatabaseDontUse
from twisted.mail import smtp
from zope.interface import implementer
from twisted.internet import defer
from twisted.mail.imap4 import LOGINCredentials, PLAINCredentials
from twisted.cred.portal import IRealm


@implementer(smtp.IMessageDelivery)
class ConsoleMessageDelivery:
    def receivedHeader(self, helo, origin, recipients):
        return "Received: ConsoleMessageDelivery"

    def validateFrom(self, helo, origin):
        # Acepta todas las direcciones
        return origin

    def validateTo(self, user):
        # Convertir la dirección completa a cadena
        # Se asume que user.dest tiene una representación que contiene '@'
        address = str(user.dest)
        try:
            local_part, recipient_domain = address.split('@')
        except ValueError:
            # Si no se puede separar en dos partes, se rechaza la dirección
            raise smtp.SMTPBadRcpt(user)

        # Verifica si el dominio está en la lista de dominios permitidos
        if recipient_domain not in self.domains:
            raise smtp.SMTPBadRcpt(user)

        # Si el dominio es válido, devuelve una función que crea un mensaje
        return lambda: ConsoleMessage()


@implementer(smtp.IMessage)
class ConsoleMessage:
    def __init__(self):
        self.lines = []

    def lineReceived(self, line):
        if isinstance(line, bytes):
            line = line.decode('utf-8', errors='replace')
        self.lines.append(line)

    def eomReceived(self):
        print("Nuevo mensaje recibido:")
        print("\n".join(self.lines))
        self.lines = None
        return defer.succeed(None)

    def connectionLost(self):
        self.lines = None


class ConsoleSMTPFactory(smtp.SMTPFactory):
    protocol = smtp.ESMTP

    def __init__(self, portal, domains, mail_storage, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.portal = portal
        self.delivery = ConsoleMessageDelivery()
        self.domains = domains
        self.mail_storage = mail_storage

    def buildProtocol(self, addr):
        p = super().buildProtocol(addr)
        p.delivery = self.delivery
        p.challengers = {"LOGIN": LOGINCredentials, "PLAIN": PLAINCredentials}
        return p



@implementer(IRealm)
class SimpleRealm:
    def requestAvatar(self, avatarId, mind, *interfaces):
        if smtp.IMessageDelivery in interfaces:
            return smtp.IMessageDelivery, ConsoleMessageDelivery(), lambda: None
        raise NotImplementedError()


def main(domains, mail_storage, port):
    # Configuración del portal y el checker para la autenticación
    portal = Portal(SimpleRealm())
    checker = InMemoryUsernamePasswordDatabaseDontUse()
    checker.addUser("guest", "password")
    portal.registerChecker(checker)

    # Crear la aplicación Twisted
    app = service.Application("Console SMTP Server")
    # Instanciar el factory pasando los parámetros leídos
    factory = ConsoleSMTPFactory(portal, domains, mail_storage)
    # Configurar el servidor TCP en el puerto indicado
    internet.TCPServer(port, factory).setServiceParent(app)
    return app



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Servidor SMTP usando Twisted")
    parser.add_argument("-d", "--domains", required=True,
                        help="Dominios aceptados (separados por comas, sin espacios).")
    parser.add_argument("-s", "--mail-storage", required=True,
                        help="Directorio donde se almacenarán los correos.")
    parser.add_argument("-p", "--port", type=int, default=2500,
                        help="Puerto en el que se ejecutará el servidor SMTP (default: 2500).")

    args = parser.parse_args()

    # Convertir la cadena de dominios en una lista
    domains = [dom.strip() for dom in args.domains.split(',')]
    mail_storage = args.mail_storage
    port = args.port

    print("Iniciando el servidor SMTP con los siguientes parámetros:")
    print("Dominios:", domains)
    print("Almacenamiento:", mail_storage)
    print("Puerto:", port)

    # Inicia la aplicación de Twisted
    application = main(domains, mail_storage, port)

    from twisted.application import service
    from twisted.internet import reactor

    # 1. Arranca el servicio
    service.IService(application).startService()

    # 2. Arranca el reactor
    reactor.run()


