import argparse
import os
import csv
from twisted.internet import reactor, protocol
from twisted.mail import imap4
from twisted.cred import portal, credentials, error
from twisted.internet.defer import succeed, fail
try:
    from twisted.cred.interfaces import ICredentialsChecker
except ImportError:
    try:
        from twisted.cred.checkers import ICredentialsChecker
    except ImportError:
        from zope.interface import Interface
        class ICredentialsChecker(Interface):
            pass
from zope.interface import implementer
from email.header import make_header, decode_header
from email.parser import BytesParser

Ruta_CSV = "/home/brandon/Documentos/UltimoSemestre/redes/CarpetasDelServer/Usuarios.csv"

def cargar_usuarios_desde_csv():
    usuarios = {}
    try:
        with open(Ruta_CSV, newline='', encoding='utf-8') as archivo:
            lector = csv.reader(archivo)
            next(lector)
            for fila in lector:
                if len(fila) >= 2:
                    print(fila)
                    user, password = fila[0].strip(), fila[1].strip()
                    usuarios[user] = password
    except FileNotFoundError:
        print(f"⚠️ No se encontró el archivo CSV en: {Ruta_CSV}. Se usará autenticación vacía.")
    return usuarios

@implementer(ICredentialsChecker)
class CSVCredentialsChecker(object):
    credentialInterfaces = (credentials.IUsernamePassword,)

    def __init__(self, csv_path):
        self.creds = {}
        self.load_csv(csv_path)

    def load_csv(self, csv_path):
        try:
            with open(csv_path, newline='', encoding='utf-8') as archivo:
                lector = csv.reader(archivo)
                next(lector)
                for fila in lector:
                    if len(fila) >= 2:
                        username = fila[0].strip()
                        password = fila[1].strip()
                        self.creds[username] = password
            print("DEBUG - Credenciales cargadas desde CSV:", self.creds, flush=True)
        except FileNotFoundError:
            print(f"DEBUG - No se encontró el archivo CSV en: {csv_path}", flush=True)

    def requestAvatarId(self, credentials_obj):
        print("DEBUG - In CSVCredentialsChecker.requestAvatarId", flush=True)
        username = (credentials_obj.username.decode('utf-8')
                    if isinstance(credentials_obj.username, bytes)
                    else credentials_obj.username)
        password = (credentials_obj.password.decode('utf-8')
                    if isinstance(credentials_obj.password, bytes)
                    else credentials_obj.password)
        print("DEBUG - Received credentials: username =", username, "password =", password, flush=True)
        if username in self.creds and self.creds[username] == password:
            print("DEBUG - Autenticación exitosa para:", username, flush=True)
            return succeed(username)
        else:
            print("DEBUG - Autenticación fallida para:", username, flush=True)
            return fail(error.UnauthorizedLogin("Invalid login"))

@implementer(imap4.IAccount)
class IMAPUserAccount:
    def __init__(self, username, maildir):
        self.username = username
        self.maildir = maildir
        self.mailbox = IMAPMailbox(maildir)

    def listMailboxes(self, ref="", wildcard="*"):
        return {"INBOX": self.mailbox}

    def select(self, name, readwrite=True):
        if name == "INBOX":
            self.mailbox.refresh()
            return self.mailbox
        return None

    def create(self, mailboxName):
        raise NotImplementedError("La creación de buzones no está implementada")

@implementer(imap4.IMailbox)
class IMAPMailbox:
    def __init__(self, path):
        self.path = path
        self.messages = self.load_messages()

    def load_messages(self):
        messages = []
        if not os.path.exists(self.path):
            print(f"⚠️ La ruta '{self.path}' no existe. Creando carpeta...", flush=True)
            os.makedirs(self.path)
        for i, filename in enumerate(sorted(os.listdir(self.path))):
            filepath = os.path.join(self.path, filename)
            if os.path.isfile(filepath):
                with open(filepath, "rb") as f:
                    content = f.read()
                    if b"Content-Type" not in content:
                        content = (b"Content-Type: text/plain; charset=utf-8\n"
                                   b"Content-Transfer-Encoding: quoted-printable\n\n") + content
                    messages.append(IMAPMessage(content, uid=i + 1))
        return messages

    def refresh(self):
        print("🔄 Refrescando buzón...", flush=True)
        self.messages = self.load_messages()

    def addListener(self, listener):
        pass

    def removeListener(self, listener):
        pass

    def fetch(self, messages, uid):
        self.refresh()
        return list({i + 1: self.messages[i] for i in range(len(self.messages))}.items())

    def expunge(self):
        return []

    def getFlags(self):
        return []

    def getMessageCount(self):
        return len(self.messages)

    def getRecentCount(self):
        return 0

    def getUIDValidity(self):
        return 1

    def getUIDNext(self):
        return 1 + len(self.messages)

    def getHierarchicalDelimiter(self):
        return "/"

    def isWriteable(self):
        return True

@implementer(imap4.IMessage)
class IMAPMessage:
    def __init__(self, content, uid=None):
        self.content = content
        self.uid = uid

    def getHeaders(self, negate, *names):
        from email import message_from_bytes
        from email.header import Header
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

    def decode_mime_header(self, raw_header):
        hdr = make_header(decode_header(raw_header))
        return hdr.encode()

    def getBodyFile(self):
        from io import BytesIO
        from email import message_from_bytes
        import quopri
        msg = message_from_bytes(self.content)
        payload = msg.get_payload(decode=True)
        encoding = msg.get_content_charset("utf-8")
        try:
            if msg["Content-Transfer-Encoding"] and "quoted-printable" in msg["Content-Transfer-Encoding"].lower():
                decoded_payload = quopri.decodestring(payload).decode(encoding)
            else:
                decoded_payload = payload.decode(encoding)
        except (UnicodeDecodeError, AttributeError):
            decoded_payload = payload.decode("utf-8", errors="replace")
        headers = self.content.split(b"\n\n", 1)[0].decode("utf-8", errors="replace")
        full_message = f"{headers}\n\n{decoded_payload}".encode("utf-8")
        return BytesIO(full_message)

    def getFlags(self):
        return []

    def getUID(self):
        return self.uid if self.uid is not None else 1

    def getSize(self):
        return len(self.content)

    def isMultipart(self):
        return False

@implementer(portal.IRealm)
class IMAPUserRealm:
    def __init__(self, mail_storage):
        self.mail_storage = mail_storage

    def requestAvatar(self, avatarId, mind, *interfaces):
        if imap4.IAccount in interfaces:
            if "@" in avatarId:
                local_part, domain = avatarId.split("@")
            else:
                print(f"⚠️ ERROR: Usuario inválido (falta dominio): {avatarId}", flush=True)
                raise credentials.UnauthorizedLogin("Formato de usuario incorrecto")
            user_maildir = os.path.join(self.mail_storage, domain, local_part)
            print(f"📂 Ruta de correos para {avatarId}: {user_maildir}", flush=True)
            print(f"✅ Login exitoso para {avatarId}", flush=True)
            return imap4.IAccount, IMAPUserAccount(avatarId, user_maildir), lambda: None
        raise NotImplementedError()

class IMAPServerProtocol(imap4.IMAP4Server):
    def __init__(self, portal):
        super().__init__()
        self.portal = portal

class IMAPServerFactory(protocol.Factory):
    def __init__(self, portal):
        self.portal = portal

    def buildProtocol(self, addr):
        return IMAPServerProtocol(self.portal)

def main():
    parser = argparse.ArgumentParser(description="Servidor IMAP basado en archivos locales.")
    parser.add_argument("-s", "--storage", required=True, help="Ruta del almacenamiento de correos.")
    parser.add_argument("-p", "--port", type=int, required=True, help="Puerto donde correrá el servidor IMAP.")
    args = parser.parse_args()

    checker = CSVCredentialsChecker(Ruta_CSV)
    realm = IMAPUserRealm(args.storage)
    p = portal.Portal(realm, [checker])

    factory = IMAPServerFactory(p)
    reactor.listenTCP(args.port, factory)
    print(f"✅ Servidor IMAP corriendo en el puerto {args.port} con almacenamiento en '{args.storage}'", flush=True)
    reactor.run()

if __name__ == '__main__':
    main()
