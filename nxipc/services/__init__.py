from ..commands import *
from ..types import ServiceStruct, HosVersion

class Service:
    name = None
    domain = False

    version = HosVersion(0,0,0)

    @classmethod
    def set_hos_version(cls, setsys):
        cls.version = setsys.get_version().hos_version

    def __init__(self, h, base=None):
        if base is None:
            self.base = h.execute(GetService, self.name)

            if self.domain:
                self.base = h.execute(ConvertServiceToDomain, self.base)
        else:
            self.base = base

        self.h = h

    @property
    def closed(self):
        return not self.base.active

    def close(self):
        #print("BLAH")
        if not self.closed:
            #print("BLAH2")
            self.h.execute(CloseService, self.base)
            ##print("closed")
            self.base.session = 0
            #print("BLAH3")
        #print("BLAH4")

    def dispatch(self, *args, **kwargs):
        out = self.h.execute(DispatchToService, self.base, *args, **kwargs)

        out["objects"] = [Service(self.h, x) for x in out["objects"]]

        return out

    def allocate(self, *args, **kwargs):
        return self.h.execute(Allocate, *args, **kwargs)

    def free(self, *args, **kwargs):
        self.h.execute(Free, *args, **kwargs)

    def read(self, *args, **kwargs):
        return self.h.execute(Read, *args, **kwargs)

    def write(self, *args, **kwargs):
        self.h.execute(Write, *args, **kwargs)

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

class SubService:
    def __init__(self, parent, srv):
        self.parent = parent
        self.srv = srv

    @property
    def closed(self):
        return self.parent.closed or self.srv.closed

    def close(self):
        ##print(type(self))
        if not self.closed:
            self.srv.close()

    @property
    def version(self):
        return self.srv.version

    def dispatch(self, *args, **kwargs):
        return self.srv.dispatch(*args, **kwargs)

    def allocate(self, *args, **kwargs):
        return self.srv.allocate(*args, **kwargs)

    def free(self, *args, **kwargs):
        self.srv.free(*args, **kwargs)

    def read(self, *args, **kwargs):
        return self.srv.read(*args, **kwargs)

    def write(self, *args, **kwargs):
        self.srv.wrtie(*args, **kwargs)

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

from .account import Account
from .audio import AudOut
from .fs import FspSrv
from .set import SetSys