from ctypes import *

from ..types import SfBufferAttr
from ..constants import curr_proc_handle
from . import Service, SubService

class AudOut(Service):
    name = b"audout:u"

    DeviceNameType = c_char * 0x100

    class Buffer(LittleEndianStructure):
        _fields_ = [
            ("next",        c_void_p),
            ("buffer",      c_void_p),
            ("buffer_size", c_uint64),
            ("data_size",   c_uint64),
            ("data_offset", c_uint64)
        ]

    class AudioOut(SubService):
        def start(self):
            self.dispatch(1)

        def stop(self):
            self.dispatch(2)

        def append_buffer(self, buffer):
            if self.version >= (3,0,0):
                cmd_id = 7
                attr = SfBufferAttr.HipcAutoSelect
            else:
                cmd_id = 3
                attr = SfBufferAttr.HipcMapAlias

            out = self.dispatch(cmd_id, c_uint64(),
                buffers=(
                    (buffer, attr),
                )
            )

    def list_audio_outs(self, count):
        if self.version >= (3,0,0):
            cmd_id = 2
            attr = SfBufferAttr.HipcAutoSelect
        else:
            cmd_id = 0
            attr = SfBufferAttr.HipcMapAlias

        out = self.dispatch(cmd_id, None, c_uint32,
            buffers=(
                (self.DeviceNameType * count, attr),
            )
        )

        return [x.value.decode() for x in out["buffers"][0][:out["out"].value]]

    def open_audio_out(self, sample_rate=0xbb80, channel_count=0x20000, name="DeviceOut"):
        class In(LittleEndianStructure):
            _fields_ = [
                ("sample_rate",   c_uint32),
                ("channel_count", c_uint32),
                ("client_pid",    c_uint64)
            ]

        class Out(LittleEndianStructure):
            _fields_ = [
                ("sample_rate",   c_uint32),
                ("channel_count", c_uint32),
                ("pcm_format",    c_uint32),
                ("state",         c_uint32)
            ]

        if self.version > (3,0,0):
            attr = SfBufferAttr.HipcAutoSelect
            cmd_id = 3
        else:
            attr = SfBufferAttr.HipcMapAlias
            cmd_id = 1

        out = self.dispatch(cmd_id, In(sample_rate, channel_count, 0), Out,
            buffers=(
                (self.DeviceNameType(*name.encode()), attr),
                (self.DeviceNameType, attr)
            ),
            in_send_pid=True,
            in_handles=(curr_proc_handle,),
            out_num_objects=1
        )

        return self.AudioOut(self, out["objects"][0]), out["buffers"][0].value.decode(), out["out"]