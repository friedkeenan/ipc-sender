import usb.core
import usb.util
import io
import enum
import ctypes

from .services import Service, SubService

class UsbCommandHandler:
    def __init__(self, idVendor=0x057e, idProduct=0x3000, timeout=3000, max_rw=0xe00):
        self.dev = usb.core.find(idVendor=idVendor, idProduct=idProduct)
        if self.dev is None:
            raise ValueError("Device not found")

        self.dev.set_configuration()
        intf = self.dev.get_active_configuration()[(0,0)]
        self.ep = (usb.util.find_descriptor(intf,
                      custom_match=lambda e:usb.util.endpoint_direction(e.bEndpointAddress)==usb.util.ENDPOINT_OUT),
                   usb.util.find_descriptor(intf,
                      custom_match=lambda e:usb.util.endpoint_direction(e.bEndpointAddress)==usb.util.ENDPOINT_IN))

        self.timeout = timeout
        self.max_rw = max_rw

        self.closed = False

    def write(self, *args):
        write_f = b"".join(bytes(x) for x in args if x is not None)
        size = len(write_f)
        if size == 0:
            return

        write_f = io.BytesIO(write_f)
        while write_f.tell() < size:
            to_write = min(size - write_f.tell(), self.max_rw)
            self.ep[0].write(write_f.read(to_write), timeout=self.timeout)

    def read(self, *args):
        if len(args) == 1 and isinstance(args[0], int):
            size = args[0]
        else:
            size = sum(ctypes.sizeof(x) for x in args if x is not None)
        
        if size == 0:
            return

        read_f = io.BytesIO()
        while read_f.tell() < size:
            to_read = min(size - read_f.tell(), self.max_rw)
            read_f.write(self.ep[1].read(to_read, timeout=self.timeout).tobytes())

        read_f.seek(0)

        if isinstance(args[0], int):
            return read_f.read(args[0])

        ret = []
        for arg in args:
            if arg is None:
                continue

            ret.append(arg.from_buffer(bytearray(read_f.read(ctypes.sizeof(arg)))))

        if len(ret) == 1:
            return ret[0]

        if len(ret) == 0:
            return None

        return ret

    def execute(self, cmd, *args, **kwargs):
        if not self.closed:
            return cmd.execute(self, *args, **kwargs)