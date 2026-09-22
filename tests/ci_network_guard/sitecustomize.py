"""CI subprocesses may contact loopback test servers, never production services."""
import ipaddress
import socket

_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex
_getaddrinfo = socket.getaddrinfo


def allowed(host):
    if host in ('localhost', 'localhost.localdomain', None):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def connect(self, address):
    if isinstance(address, tuple) and not allowed(address[0]):
        raise OSError('CI blocks non-loopback network connections')
    return _connect(self, address)


def connect_ex(self, address):
    if isinstance(address, tuple) and not allowed(address[0]):
        raise OSError('CI blocks non-loopback network connections')
    return _connect_ex(self, address)


def getaddrinfo(host, *args, **kwargs):
    if not allowed(host):
        raise OSError('CI blocks non-loopback DNS resolution')
    return _getaddrinfo(host, *args, **kwargs)


socket.socket.connect = connect
socket.socket.connect_ex = connect_ex
socket.getaddrinfo = getaddrinfo
