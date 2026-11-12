"""Preview builds: block non-loopback network and start the clock at CHUMEI_PREVIEW_NOW.

Loaded through PYTHONPATH by build_preview.py so the baseline and the candidate
are built against the same fixed moment without touching product code.
"""
import datetime as _dt
import ipaddress
import os
import socket
import time as _time


def _allowed(host):
    if host in ('localhost', 'localhost.localdomain', None):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


_connect, _connect_ex, _getaddrinfo = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo


def _guard(address):
    if isinstance(address, tuple) and not _allowed(address[0]):
        raise OSError('preview build blocks non-loopback network connections')


socket.socket.connect = lambda self, address: (_guard(address), _connect(self, address))[1]
socket.socket.connect_ex = lambda self, address: (_guard(address), _connect_ex(self, address))[1]


def _getaddrinfo_guarded(host, *args, **kwargs):
    if not _allowed(host):
        raise OSError('preview build blocks non-loopback DNS resolution')
    return _getaddrinfo(host, *args, **kwargs)


socket.getaddrinfo = _getaddrinfo_guarded

_now = os.environ.get('CHUMEI_PREVIEW_NOW')
if _now:
    _real_dt, _real_date, _real_time = _dt.datetime, _dt.date, _time.time
    _offset = _real_dt.fromisoformat(_now).timestamp() - _real_time()

    def _fake_time():
        return _real_time() + _offset

    class _FrozenDateTime(_real_dt):
        @classmethod
        def now(cls, tz=None):
            return _real_dt.fromtimestamp(_fake_time(), tz)

        @classmethod
        def utcnow(cls):
            return _real_dt.fromtimestamp(_fake_time(), _dt.timezone.utc).replace(tzinfo=None)

        @classmethod
        def today(cls):
            return _real_dt.fromtimestamp(_fake_time())

    class _FrozenDate(_real_date):
        @classmethod
        def today(cls):
            return _real_date.fromtimestamp(_fake_time())

    _time.time = _fake_time
    _dt.datetime = _FrozenDateTime
    _dt.date = _FrozenDate
