from ctypes import *

from ..types import SfBufferAttr, HosVersion
from . import Service

class SetSys(Service):
    name = b"set:sys"

    class FirmwareVersion(LittleEndianStructure):
        _fields_ = [
            ("major",           c_uint8),
            ("minor",           c_uint8),
            ("micro",           c_uint8),
            ("padding1",        c_uint8),
            ("revision_major",  c_uint8),
            ("revision_minor",  c_uint8),
            ("padding2",        c_uint8),
            ("padding3",        c_uint8),
            ("platform",        c_char * 0x20),
            ("version_hash",    c_char * 0x40),
            ("display_version", c_char * 0x18),
            ("display_title",   c_char * 0x80)
        ]

        @property
        def hos_version(self):
            return HosVersion(self.major, self.minor, self.micro)

    def get_version(self):
        if self.version >= (3,0,0):
            cmd_id = 4
        else:
            cmd_id = 3

        out = self.dispatch(cmd_id,
            buffers=(
                (self.FirmwareVersion, SfBufferAttr.FixedSize | SfBufferAttr.HipcPointer),
            )
        )

        return out["buffers"][0]