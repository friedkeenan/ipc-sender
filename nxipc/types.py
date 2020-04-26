import enum
from ctypes import *

Handle = c_uint32

class Result(Union):
    class Split(LittleEndianStructure):
        _fields_ = [
            ("module",      c_uint32, 9),
            ("description", c_uint32, 13)
        ]

    _anonymous_ = ("split",)
    _fields_ = [
        ("value", c_uint32),
        ("split", Split)
    ]

    def __eq__(self, other):
        if not isinstance(other, int):
            other = other.value

        return self.value == other

    def __str__(self):
        return f"2{self.module:03}-{self.description:04} ({self.value:#x})"

    def __repr__(self):
        return f"Result({str(self)})"

class ServiceStruct(LittleEndianStructure):
    _fields_ = [
        ("session",             Handle),
        ("own_handle",          c_uint32),
        ("object_id",           c_uint32),
        ("pointer_buffer_size", c_uint16)
    ]

    @property
    def active(self):
        return self.session != 0

    @property
    def is_override(self):
        return self.active and self.own_handle == 0 and self.object_id == 0

    @property
    def is_domain(self):
        return self.active and self.own_handle != 0 and self.object_id != 0

    @property
    def is_domain_subservice(self):
        return self.active and self.own_handle == 0 and self.object_id != 0

class SfBufferAttr(enum.Enum):
    In                             = 1 << 0
    Out                            = 1 << 1
    HipcMapAlias                   = 1 << 2
    HipcPointer                    = 1 << 3
    FixedSize                      = 1 << 4
    HipcAutoSelect                 = 1 << 5
    HipcMapTransferAllowsNonSecure = 1 << 6
    HipcMapTransferAllowsNonDevice = 1 << 7

    def __or__(self, other):
        if isinstance(other, enum.Enum):
            other = other.value

        return self.value | other

class SfBuffer(LittleEndianStructure):
    _fields_ = [
        ("ptr",  c_void_p),
        ("size", c_uint64),
    ]

class SfOutHandleAttr(enum.Enum):
    Blank    = 0
    HipcCopy = 1
    HipcMove = 2

class SmServiceName(Union):
    _fields_ = [
        ("name", c_char * 8),
    ]

class ResultException(Exception):
    def __init__(self, result):
        super().__init__(str(result))

        self.result = result

class HosVersion:
    def __init__(self, major, minor, micro):
        self.major = major
        self.minor = minor
        self.micro = micro

    @property
    def packed(self):
        return (self.major << 16) | (self.minor << 8) | self.micro

    def __eq__(self, other):
        if not isinstance(other, HosVersion):
            other = type(self)(other[0], other[1], other[1])

        return self.packed == other.packed

    def __gt__(self, other):
        if not isinstance(other, HosVersion):
            other = type(self)(other[0], other[1], other[1])

        return self.packed > other.packed

    def __lt__(self, other):
        if not isinstance(other, HosVersion):
            other = type(self)(other[0], other[1], other[1])

        return self.packed < other.packed

    def __ge__(self, other):
        return self > other or self == other

    def __le__(self, other):
        return self < other or self == other

    def __str__(self):
        return f"{self.major}.{self.minor}.{self.micro}"

    def __repr__(self):
        return f"HosVersion({str(self)})"