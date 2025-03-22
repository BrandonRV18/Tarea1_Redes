import argparse
import os
import csv
from twisted.internet import reactor, protocol
from twisted.mail import imap4
from twisted.cred import portal, credentials, error
from twisted.internet.defer import succeed, fail
from twisted.cred.checkers import ICredentialsChecker
from zope.interface import implementer
from email.header import make_header, decode_header
from email import message_from_bytes
from email.header import Header
from io import BytesIO

# Ruta del archivo CSV con las credenciales de los usuarios.
UsersPathCSV = "/home/ec2-user/Tarea1/Tarea1_Redes/ServerIMAP/Usuarios.csv"


@implementer(ICredentialsChecker)
class CredentialsCheckerCSV(object):
    credentialInterfaces = (credentials.IUsernamePassword,)

    def __init__(self, csv_path):
        """
        Gestiona la carga de credenciales desde un archivo CSV.
        Entradas: csv_path (la ruta del CSV)
        Salidas: Ninguna
        """
        self.creds = {}
        self.loadCsv(csv_path)

    def loadCsv(self, csv_path):
        """
        Carga las credenciales del archivo CSV en un diccionario.
        Entradas: csv_path
        Salidas: Ninguna
        """
        try:
            with open(csv_path, newline='', encoding='utf-8') as archivo:
                lector = csv.reader(archivo)
                next(lector)
                for fila in lector:
                    username = fila[0].strip()
                    password = fila[1].strip()
                    self.creds[username] = password
        except FileNotFoundError:
            print(f"No se encontró el archivo CSV en: {csv_path}")

    def requestAvatarId(self, credentials_obj):
        """
        Verifica las credenciales y retorna el ID del avatar si son válidas.
        Entradas: credentials_obj (objeto con los datos: username y password)
        Salida: Deferred con username o falla con UnauthorizedLogin
        """
        username = (credentials_obj.username.decode('utf-8')
                    if isinstance(credentials_obj.username, bytes)
                    else credentials_obj.username)

        password = (credentials_obj.password.decode('utf-8')
                    if isinstance(credentials_obj.password, bytes)
                    else credentials_obj.password)

        if username in self.creds and self.creds[username] == password:
            return succeed(username)
        else:
            return fail(error.UnauthorizedLogin("Invalid login"))


@implementer(imap4.IAccount)
class IMAPUserAccount:
    def __init__(self, username, mailPath):
        """
        Inicializa la cuenta de usuario con su nombre y ruta de correos
        Entradas: username, mailPath
        Salidas: Ninguna
        """
        self.username = username
        self.mailPath = mailPath
        self.mailbox = IMAPMailbox(mailPath)

    def listMailboxes(self, ref="", wildcard="*"):
        """
        Lista los buzones disponibles para el usuario (Solo INBOX en este caso)
        Entradas: ref , wildcard
        Salidas: diccionario con el buzon INBOX
        """
        return {"INBOX": self.mailbox}

    def select(self, name, readwrite=True):
        """
        Selecciona y refresca el buzón especificado (INBOX)
        Entradas: name (nombre del buzon), readwrite
        Salidas: El buzón "INBOX" o ninguna
        """
        if name == "INBOX":
            self.mailbox.refresh()
            return self.mailbox
        return None

    def create(self, mailboxName):
        """
        Método para crear nuevos buzones (no implementado).
        Entradas: mailboxName
        Salidas: Ninguna
        """
        raise NotImplementedError("La creación de buzones no está implementada")


@implementer(imap4.IMailbox)
class IMAPMailbox:
    def __init__(self, path):
        """
        Inicializa el buzón estableciendo la ruta de almacenamiento y cargando los mensajes.
        Entradas: path (La ruta)
        Salidas: Ninguna
        """
        self.path = path
        self.messages = self.loadMessages()

    def loadMessages(self):
        """
        Carga los mensajes desde la ruta de almacenamiento.
        Entradas: Ninguna
        Salidas: lista con los mensajes
        """
        messages = []
        if not os.path.exists(self.path):
            return messages

        for i, filename in enumerate(sorted(os.listdir(self.path))):
            filepath = os.path.join(self.path, filename)
            if os.path.isfile(filepath):
                with open(filepath, "rb") as f:
                    content = f.read()
                    messages.append(IMAPMessage(content, uid=i + 1))
        return messages

    def refresh(self):
        """
        Recarga los mensajes.
        Entradas: Ninguna
        Salidas: Ninguna
        """
        self.messages = self.loadMessages()

    def addListener(self, listener):
        """
        Listener para eventos del buzón (No implementado).
        """
        pass

    def removeListener(self, listener):
        """
        Elimina un listener de los eventos del buzón (No implementado).
        """
        pass

    def fetch(self, messages, uid):
        """
        Retorna una lista con el UID y el mensaje tras refrescar el buzón.
        Entradas: messages (lista), uid (int)
        Salidas: Una lista con el mensaje y su identificador
        """
        self.refresh()
        return list({i + 1: self.messages[i] for i in range(len(self.messages))}.items())

    def expunge(self):
        """
        Elimina mensajes marcados para borrado (No implementado).
        """
        return []

    def getFlags(self):
        """
        Retorna la lista de flags del buzón (No implementado).
        """
        return []

    def getMessageCount(self):
        """
        Retorna el número total de mensajes en el buzón.
        Entradas: Ninguna
        Salidas: Cantidad de mensajes
        """
        return len(self.messages)

    def getRecentCount(self):
        """
        Retorna el número de mensajes recientes en el buzón (Siempre será 0).
        """
        return 0

    def getUIDValidity(self):
        """
        Retorna un valor fijo para el UIDVALIDITY del buzón.
        """
        return 1

    def getUIDNext(self):
        """
        Retorna el siguiente UID a asignar a un mensaje nuevo.
        Entradas: Ninguna
        Salidas: 1 + cantidad actual de mensajes
        """
        return 1 + len(self.messages)

    def getHierarchicalDelimiter(self):
        """
        Retorna el delimitador jerárquico del buzón.
        Entradas: Ninguna
        Salidas:  el /
        """
        return "/"

    def isWriteable(self):
        """
        Indica si el buzón es escribible.
        Entradas: Ninguna
        Salidas: True
        """
        return True


@implementer(imap4.IMessage)
class IMAPMessage:
    def __init__(self, content, uid=None):
        """
        Inicializa el mensaje con su contenido y un UID opcional.
        Entradas: content (bytes), uid (int, opcional)
        Salidas: Ninguna
        """
        self.content = content
        self.uid = uid

    def getHeaders(self, negate, *names):
        """
        Retorna los encabezados solicitados del mensaje, en este caso, From, To, Subject y Date.
        Entradas: negate, *names (lista de los nombres de los encabezados)
        Salidas: Los encabezados
        """
        msg = message_from_bytes(self.content)
        headers = {}
        if not names:
            names = [b"From", b"To", b"Subject", b"Date"]
        for name in names:
            header_name = name.decode("utf-8") if isinstance(name, bytes) else name
            if msg[header_name]:
                if header_name.lower() == "subject":
                    headers[header_name] = Header(str(make_header(decode_header(msg[header_name]))), "utf-8").encode()
                else:
                    headers[header_name] = str(make_header(decode_header(msg[header_name])))
        return headers

    def getBodyFile(self):
        """
        Retorna un objeto BytesIO que contiene el mensaje completo (encabezados y cuerpo).
        Entradas: Ninguna
        Salidas: Contenido completo del mensaje en bytes
        """
        msg = message_from_bytes(self.content)
        body_bytes = msg.get_payload(decode=True) or b''
        body_str = body_bytes.decode(msg.get_content_charset('utf-8'), errors='replace')
        headers = self.content.split(b"\n\n", 1)[0]
        return BytesIO(headers + b"\n\n" + body_str.encode('utf-8'))

    def getFlags(self):
        """
        Retorna la lista de flags del mensaje (No se implementó)
        """
        return []

    def getUID(self):
        """
        Retorna el UID del mensaje.
        Entradas: Ninguna
        Salidas: UID o 1
        """
        return self.uid if self.uid is not None else 1

    def getSize(self):
        """
        Retorna el tamaño del mensaje
        Entradas: Ninguna
        Salidas: tamaño del mensaje
        """
        return len(self.content)

    def isMultipart(self):
        """
        Indica si el mensaje es multipart  (No se implementó)
        """
        return False


@implementer(portal.IRealm)
class IMAPUserRealm:
    def __init__(self, mail_storage):
        """
        Inicializa el realm con la ruta para el almacenamiento de correos.
        Entradas: mail_storage
        Salidas: Ninguna
        """
        self.mail_storage = mail_storage

    def requestAvatar(self, avatarId, mind, *interfaces):
        """
        Retorna una instancia de cuenta IMAP para el avatar solicitado.
        Entradas: avatarId , mind, *interfaces
        Salidas: interfaz, instancia de IMAPUserAccount y funcion de limpieza
        """
        if imap4.IAccount in interfaces:
            if "@" in avatarId:
                local_part, domain = avatarId.split("@")
            else:
                raise credentials.UnauthorizedLogin("Formato de usuario incorrecto")
            user_maildir = os.path.join(self.mail_storage, domain, local_part)
            return imap4.IAccount, IMAPUserAccount(avatarId, user_maildir), lambda: None
        raise NotImplementedError()



class IMAPServerProtocol(imap4.IMAP4Server):
    def __init__(self, portal):
        """
        Inicializa el protocolo IMAP asignando el portal.
        Entradas: portal
        Salidas: Ninguna
        """
        super().__init__()
        self.portal = portal


class IMAPServerFactory(protocol.Factory):
    def __init__(self, portal):
        """
        Inicializa Faatory con el portal de autenticación.
        Entradas: portal
        Salidas: Ninguna
        """
        self.portal = portal

    def buildProtocol(self, addr):
        """
        Crea y retorna una instancia del protocolo IMAPServerProtocol para una conexión entrante.
        Entradas: addr (dirección del cliente)
        Salidas: una instancia de IMAPServerProtocol
        """
        return IMAPServerProtocol(self.portal)


def main():
    """
    Configura el servidor IMAP.
    Entradas: Ninguna
    Salidas: Inicia el reactor y corre el servidor IMAP
    """
    parser = argparse.ArgumentParser(description="Servidor IMAP basado en archivos locales.")
    parser.add_argument("-s", "--storage", required=True, help="Ruta del almacenamiento de correos.")
    parser.add_argument("-p", "--port", type=int, required=True, help="Puerto donde correrá el servidor IMAP.")
    args = parser.parse_args()

    checker = CredentialsCheckerCSV(UsersPathCSV)
    realm = IMAPUserRealm(args.storage)
    p = portal.Portal(realm, [checker])

    factory = IMAPServerFactory(p)
    reactor.listenTCP(args.port, factory)
    print(f"Servidor IMAP corriendo en el puerto {args.port} con almacenamiento en '{args.storage}'", flush=True)
    reactor.run()


if __name__ == '__main__':
    main()
