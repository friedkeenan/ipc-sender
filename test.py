#!/usr/bin/env python3

import nxipc

import math
import audioread
from ctypes import *

def do_acc_stuff(h):
    acc = nxipc.services.Account(h)

    uids = acc.list_all_users()

    profile = acc.get_profile(uids[0])

    im = profile.get_image()
    im.show()

def do_audout_stuff(h):
    audout = nxipc.services.AudOut(h)

    print(audout.list_audio_outs(2))

    with audioread.audio_open("test2.flac") as f:
        audio_out, name, out = audout.open_audio_out()
        print(out.sample_rate, out.channel_count, name)
        input()

        data_size = out.sample_rate * out.channel_count * sizeof(c_int16) * f.duration
        data_size = math.ceil(data_size)

        buffer_size = nxipc.util.align(data_size, 0x1000)

        data = audout.allocate("memalign", buffer_size, 0x1000)

        f.channels = out.channel_count
        f.samplerate = out.sample_rate

        offset = 0
        for buf in f:
            audout.write(c_void_p(data.value + offset), buf)
            offset += len(buf)

    print(hex(data.value), hex(data_size), hex(buffer_size))

    buffer = audout.Buffer(
        buffer=data,
        buffer_size=buffer_size,
        data_size=data_size
    )

    audio_out.start()
    audio_out.append_buffer(buffer)

    input()
    audio_out.stop()
    audout.free(data)

def do_fs_stuff(h):
    fs = nxipc.services.FspSrv(h)

    bis = fs.open_bis_fs(fs.BisPartitionId.User)
    bis.tree()

    # For some reason that I cannot for the life of me figure out,
    # not doing this or doing gc.collect() will result in the fs
    # and bis objects not being closed until the end of the program,
    # at which point it is too late for them to be really closed
    bis.close()
    fs.close()

def main():
    h = nxipc.UsbCommandHandler()

    with nxipc.services.SetSys(h) as setsys:
        nxipc.Service.set_hos_version(setsys)

    do_fs_stuff(h)
    do_acc_stuff(h)

    input()
    h.execute(nxipc.commands.Exit)

if __name__ == "__main__":
    main()