from ctypes import *

from .types import *

class Command:
    id     = None # Id for the command
    Input  = None # Input struct type for the command
    Output = None # Output struct type for the command

    @classmethod
    def execute(cls, h, *args, **kwargs):
        if cls.Input is not None:
            if len(args) == 1 and isinstance(args[0], cls.Input):
                input = args[0]
            else:
                input = cls.Input(*args, **kwargs)
        else:
            input = None

        h.write(c_uint8(cls.id))
        h.write(input)

        result = h.read(Result)
        if result.value != 0:
            raise ResultException(result)

        return h.read(cls.Output)

class Exit(Command):
    id = 0

    @classmethod
    def execute(cls, h):
        super().execute(h)

        h.closed = True

class Allocate(Command):
    id = 1

    class Allocation(LittleEndianStructure):
        _fields_ = [
            ("type", c_uint8),
            ("size", c_uint64),
        ]

    @classmethod
    def execute(cls, h, alloc, size_or_type, align=None):
        if isinstance(size_or_type, int):
            size = size_or_type
        else:
            size = sizeof(size_or_type)

        h.write(c_uint8(cls.id))
        h.write(cls.Allocation({
                "malloc":   0,
                "calloc":   1,
                "memalign": 2,
            }[alloc],
            size
        ))

        if alloc == "memalign":
            h.write(c_uint64(align))

        result = h.read(Result)
        if result.value != 0:
            raise ResultException(result)

        return h.read(c_void_p)

class Free(Command):
    id    = 2
    Input = c_void_p

class Read(Command):
    id = 3

    class Info(LittleEndianStructure):
        _fields_ = [
            ("ptr",  c_void_p),
            ("size", c_uint64)
        ]

    @classmethod
    def execute(cls, h, ptr, size_or_type):
        if isinstance(size_or_type, int):
            size = size_or_type
        else:
            size = sizeof(size_or_type)

        h.write(c_uint8(cls.id))
        h.write(cls.Info(ptr, size))

        result = h.read(Result)
        if result.value != 0:
            raise ResultException(result)

        return h.read(size_or_type)

class Write(Command):
    id = 4

    class Info(LittleEndianStructure):
        _fields_ = [
            ("ptr",  c_void_p),
            ("size", c_uint64)
        ]

    @classmethod
    def execute(cls, h, ptr, to_write):
        if isinstance(to_write, (bytes, bytearray)):
            size = len(to_write)
        else:
            size = sizeof(to_write)

        h.write(c_uint8(cls.id))
        h.write(cls.Info(ptr, size))

        h.write(to_write)

        result = h.read(Result)
        if result.value != 0:
            raise ResultException(result)

class GetService(Command):
    id     = 5
    Input  = SmServiceName
    Output = ServiceStruct

class CloseService(Command):
    id    = 6
    Input = ServiceStruct

class ConvertServiceToDomain(Command):
    id     = 7
    Input  = ServiceStruct
    Output = ServiceStruct

class DispatchToService(Command):
    id = 8

    class Header(LittleEndianStructure):
        _fields_ = [
            ("service",    ServiceStruct),
            ("request_id", c_uint32),
            ("in_size",    c_uint32),
            ("out_size",   c_uint32),

            ("target_session",  Handle),
            ("context",         c_uint32),
            ("num_buffers",     c_uint8),
            ("in_send_pid",     c_bool),
            ("in_num_objects",  c_uint8),
            ("in_num_handles",  c_uint8),
            ("out_num_objects", c_uint32),
            ("out_num_handles", c_uint8)
        ]

    class Buffer(LittleEndianStructure):
        _fields_ = [
            ("size",       c_uint64),
            ("attr",       c_uint32),
            ("is_pointer", c_bool)
        ]

    @classmethod
    def execute(cls, h, service, request_id, in_data=None, out_type=None, *,
                target_session=0, context=0, buffers=(), in_send_pid=False,
                in_objects=(), in_handles=(), out_num_objects=0, out_num_handles=0):
        if in_data is None:
            in_size = 0
        else:
            in_size = sizeof(in_data)

        if out_type is None:
            out_size = 0
        else:
            out_size = sizeof(out_type)

        header = cls.Header(service, request_id, in_size, out_size,
                            target_session, context, len(buffers), in_send_pid,
                            len(in_objects), len(in_handles), out_num_objects, out_num_handles)

        h.write(c_uint8(cls.id))
        h.write(header)

        h.write(in_data)

        buffer_attrs = []
        for first, attr in buffers:
            if isinstance(attr, enum.Enum):
                attr = attr.value

            if isinstance(first, int):
                real_size = first
                attr |= SfBufferAttr.Out.value
            elif isinstance(first, tuple):
                real_size = first[1]
                first = first[0]
            elif isinstance(first, type):
                real_size = sizeof(first)
                attr |= SfBufferAttr.Out.value
            elif isinstance(first, (bytes, bytearray)):
                real_size = len(first)
                attr |= SfBufferAttr.In.value
            else:
                real_size = sizeof(first)
                attr |= SfBufferAttr.In.value

            buffer_attrs.append(attr)

            is_pointer = isinstance(first, c_void_p)

            h.write(cls.Buffer(real_size, attr, is_pointer))

            if is_pointer:
                h.write(first)
            elif attr & SfBufferAttr.In.value:
                h.write(first)

        for handle in in_handles:
            h.write(handle)

        result = h.read(Result)
        if result.value != 0:
            raise ResultException(result)

        out = {
            "buffers": [],
            "objects": [],
        }

        out["out"] = h.read(out_type)

        if out_num_objects > 0:
            out["objects"] = list(h.read(ServiceStruct * out_num_objects))

        for i, attr in enumerate(buffer_attrs):
            first = buffers[i][0]

            if isinstance(first, tuple):
                continue

            if attr & SfBufferAttr.Out.value:
                out["buffers"].append(h.read(first))

        return out