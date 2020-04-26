import io
from PIL import Image
from ctypes import *

from ..types import SfBufferAttr
from . import Service, SubService

class Account(Service):
    name = b"acc:u1"

    user_list_size = 8

    class Uid(LittleEndianStructure):
        _fields_ = [
            ("uid", c_uint64 * 2)
        ]

        @property
        def valid(self):
            return self.uid[0] != 0 or self.uid[1] != 0

    class Profile(SubService):
        def get_image_size(self):
            out = self.dispatch(10, None, c_uint32)

            return out["out"].value

        def get_image(self):
            out = self.dispatch(11, None, c_uint32,
                buffers=(
                    (self.get_image_size(), SfBufferAttr.HipcMapAlias),
                )
            )

            return Image.open(io.BytesIO(out["buffers"][0]))

    def list_all_users(self):
        out = self.dispatch(2,
            buffers=((self.Uid * self.user_list_size, SfBufferAttr.HipcPointer),)
        )

        return [x for x in out["buffers"][0] if x.valid]

    def get_profile(self, uid):
        out = self.dispatch(5, uid,
            out_num_objects=1,
        )

        return self.Profile(self, out["objects"][0])