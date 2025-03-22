import argparse
from twisted.application import internet, service
from twisted.cred.portal import Portal
from twisted.cred.checkers import InMemoryUsernamePasswordDatabaseDontUse
from twisted.mail import smtp
from zope.interface import implementer
from twisted.internet import defer
from twisted.mail.imap4 import LOGINCredentials, PLAINCredentials
from twisted.cred.portal import IRealm
from twisted.application import service
from twisted.internet import reactor
import os, time

@implementer(smtp.IMessageDelivery)
class ConsoleMessageDelivery:
    def __init__(self, domains, storage_path):
        """
        Se encarga de validar los remitentes y destinatarios.
        Entradas: domains (lista de los dominios permitidos), storage_path (ruta donde se almacenan los correos)
        Salidas: None
        """
        self.domains = domains
        self.storage_path = storage_path

    def receivedHeader(self, helo, origin, recipients):
        """
        Retorna el encabezado 'Received'.
        Entradas: helo, origin, recipients (No se utilizan en este caso)
        Salidas: el encabezado
        """
        return "Received: ConsoleMessageDelivery"

    def validateFrom(self, helo, origin):
        """
        Se encarga de validar el remitente, en este caso no se implementa.
        Entradas: helo, origin
        Salidas: origin
        """
        return origin

    def validateTo(self, user):
        """
        Se encarga de validar el destinatario y retornar función para crear un objeto ConsoleMessage.
        Entradas: user (infromacion del destinatario)
        Salidas: Una funcion lambda que crea una instancia ConsoleMessage
        """
        address = str(user.dest)
        try:
            local_part, recipient_domain = address.split('@')
        except ValueError:
            raise smtp.SMTPBadRcpt(user)
        if recipient_domain not in self.domains:
            raise smtp.SMTPBadRcpt(user)
        return lambda: ConsoleMessage(self.storage_path, local_part, recipient_domain)

@implementer(smtp.IMessage)
class ConsoleMessage:
    def __init__(self, storage_path, local_part, recipient_domain):
        """
        Inicializa el mensaje SMTP.
        Entradas: storage_path (Ruta donde se va a almacenar), local_part (parte antes del @ del correo), recipient_domain (dominio del correo)
        Salidas: None
        """
        self.storage_path = storage_path
        self.local_part = local_part
        self.recipient_domain = recipient_domain
        self.lines = []

    def lineReceived(self, line):
        """
        Procesa cada línea del mensaje.
        Entradas: line (La linea del mensaje)
        Salidas: Ninguuna
        """
        if isinstance(line, bytes):
            line = line.decode('utf-8', errors='replace')
        self.lines.append(line)

    def eomReceived(self):
        """
        Finaliza y guarda el mensaje en un archivo .eml.
        Entradas: Ninguna
        Salidas: Deferred indicando finalización exitosa
        """
        filename = f"{self.local_part}_{int(time.time())}.eml"
        directory_path = os.path.join(self.storage_path, self.recipient_domain, self.local_part)
        os.makedirs(directory_path, exist_ok=True)
        filepath = os.path.join(directory_path, filename)
        with open(filepath, "w") as f:
            f.write("\n".join(self.lines))
        print(f"Correo guardado en: {filepath}")
        self.lines = None
        return defer.succeed(None)

class ConsoleSMTPFactory(smtp.SMTPFactory):
    protocol = smtp.ESMTP

    def __init__(self, portal, domains, mail_storage, *args, **kwargs):
        """
        Inicializa el Factory con portal, dominios y ruta de almacenamiento.
        Entradas: portal, domains, mail_storage , args, kwargs
        Salidas: Ninuguna
        """
        super().__init__(*args, **kwargs)
        self.portal = portal
        self.delivery = ConsoleMessageDelivery(domains, mail_storage)
        self.domains = domains
        self.mail_storage = mail_storage

    def buildProtocol(self, addr):
        """
        Construye y configura el protocolo SMTP.
        Entradas: addr (dirección del cliente)
        Salidas: Instancia del protocolo SMTP configurado
        """
        p = super().buildProtocol(addr)
        p.delivery = self.delivery
        p.challengers = {
            b"LOGIN": LOGINCredentials,
            b"PLAIN": PLAINCredentials
        }
        return p

@implementer(IRealm)
class SimpleRealm:
    def requestAvatar(self, avatarId, mind, *interfaces):
        """
        Retorna el avatar con IMessageDelivery.
        Entradas: avatarId, mind, interfaces
        Salidas: Una instancia de ConsoleMessageDelivery(), la interfaz IMessageDelivery y una funcion lambda para limpiar
        """
        if smtp.IMessageDelivery in interfaces:
            return smtp.IMessageDelivery, ConsoleMessageDelivery(), lambda: None
        raise NotImplementedError()


def main(domains, mail_storage, port):
    """
    Se encarga de configurar la autenticación, servidor SMTP y servicio de red.
    Entradas: domains, mail_storage, port (el puerto que se va a utilizar)
    Salidas: Objeto de aplicación de Twisted
    """
    portal = Portal(SimpleRealm())
    checker = InMemoryUsernamePasswordDatabaseDontUse()
    checker.addUser("guest", "password")
    portal.registerChecker(checker)
    app = service.Application("Console SMTP Server")
    factory = ConsoleSMTPFactory(portal, domains, mail_storage)
    internet.TCPServer(port, factory).setServiceParent(app)
    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Servidor SMTP")
    parser.add_argument("-d", "--domains", required=True,
                        help="Dominios aceptados (separados por comas, sin espacios).")
    parser.add_argument("-s", "--mail-storage", required=True,
                        help="Directorio donde se almacenarán los correos.")
    parser.add_argument("-p", "--port", type=int, default=2525,
                        help="Puerto en el que se ejecutará el servidor SMTP (default: 2500).")
    args = parser.parse_args()
    domains = [dom.strip() for dom in args.domains.split(',')]
    mail_storage = args.mail_storage
    port = args.port
    print("Iniciando el servidor SMTP con los siguientes parámetros:")
    print("Dominios:", domains)
    print("Almacenamiento:", mail_storage)
    print("Puerto:", port)
    application = main(domains, mail_storage, port)
    service.IService(application).startService()
    reactor.run()
