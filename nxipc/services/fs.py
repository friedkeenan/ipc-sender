import io
import stat
import enum
import fs, fs.base, fs.subfs
import datetime as dt
from ctypes import *

from .. import util
from ..types import SfBufferAttr, ResultException
from . import Service, SubService

class FspSrv(Service):
    name = b"fsp-srv"
    domain = True

    class BisPartitionId(enum.Enum):
        BootPartition1Root              = 0
        BootPartition2Root              = 10
        UserDataRoot                    = 20
        BootConfigAndPackage2Part1      = 21
        BootConfigAndPackage2Part2      = 22
        BootConfigAndPackage2Part3      = 23
        BootConfigAndPackage2Part4      = 24
        BootConfigAndPackage2Part5      = 25
        BootConfigAndPackage2Part6      = 26
        CalibrationBinary               = 27
        CalibrationFile                 = 28
        SafeMode                        = 29
        User                            = 30
        System                          = 31
        SystemProperEncryption          = 32
        SystemProperPartition           = 33
        SignedSystemPartitionOnSafeMode = 34

    class FileSystem(SubService, fs.base.FS):
        class FileTimestamp(LittleEndianStructure):
            _fields_ = [
                ("created",  c_uint64),
                ("modified", c_uint64),
                ("accessed", c_uint64),
                ("is_valid", c_bool),
                ("padding",  c_uint8 * 7)
            ]

        PathType = c_char * 0x301

        class File(SubService, io.IOBase):
            def __init__(self, mode, *args, **kwargs):
                super().__init__(*args, **kwargs)

                if "a" in mode:
                    self.pos = self.size()
                else:
                    self.pos = 0

                self.mode = mode

            def seekable(self):
                return True

            def readable(self):
                return "r" in self.mode

            def writable(self):
                return "w" in self.mode or "a" in self.mode

            def read(self, size=-1, offset=None, option=0):
                if offset is None:
                    offset = self.tell()
                else:
                    self.seek(offset)

                if size < 0:
                    size = self.size() - offset

                class In(LittleEndianStructure):
                    _fields_ = [
                        ("option", c_uint32),
                        ("pad",    c_uint32),
                        ("offset", c_int64),
                        ("size",   c_uint64)
                    ]

                out = self.dispatch(0, In(option, 0, offset, size), c_uint64,
                    buffers=(
                        (size, SfBufferAttr.HipcMapAlias | SfBufferAttr.HipcMapTransferAllowsNonSecure),
                    )
                )

                bytes_read = out["out"].value
                self.seek(bytes_read, 1)

                return out["buffers"][0][:bytes_read]

            def write(self, b, offset=None, flush=False):
                if offset is None:
                    offset = self.tell()
                else:
                    self.seek(offset)

                if flush:
                    option = 1
                else:
                    option = 0

                if isinstance(b, str):
                    b = b.encode()

                size = len(b)

                class In(LittleEndianStructure):
                    _fields_ = [
                        ("option", c_uint32),
                        ("pad",    c_uint32),
                        ("offset", c_int64),
                        ("size",   c_uint64)
                    ]

                out = self.dispatch(1, In(option, 0, offset, size),
                    buffers=(
                        (b, SfBufferAttr.HipcMapAlias | SfBufferAttr.HipcMapTransferAllowsNonSecure),
                    )
                )

                self.seek(size, 1)

                return size

            def flush(self):
                self.dispatch(2)

            def set_size(self, size):
                self.dispatch(3, c_int64(size))

            def truncate(self, pos=None):
                if pos is None:
                    pos = self.tell()

                self.set_size(pos)

                return pos

            def size(self):
                out = self.dispatch(4, None, c_int64)

                return out["out"].value

            def seek(self, pos, whence=0):
                if whence == 0:
                    self.pos = pos
                elif whence == 1:
                    self.pos += pos
                elif whence == 2:
                    self.pos = self.size() + pos

                return self.pos

        class Directory(SubService):
            class Entry(LittleEndianStructure):
                _fields_ = [
                    ("raw_name", c_char * 0x301),
                    ("pad",  c_uint8 * 3),
                    ("type", c_int8),
                    ("pad2", c_uint8 * 3),
                    ("size", c_int64)
                ]

                @property
                def is_file(self):
                    return self.type == 1

                @property
                def name(self):
                    return self.raw_name.decode()

            def read(self, max_entries=None):
                if max_entries is None:
                    max_entries = self.entry_count()

                if max_entries == 0:
                    return []

                out = self.dispatch(0, None, c_int64,
                    buffers=(
                        (self.Entry * max_entries, SfBufferAttr.HipcMapAlias),
                    )
                )

                return list(out["buffers"][0][:out["out"].value])

            def entry_count(self):
                out = self.dispatch(1, None, c_int64)

                return out["out"].value

        def __init__(self, *args, **kwargs):
            SubService.__init__(self, *args, **kwargs)
            fs.base.FS.__init__(self)

        def close(self):
            if not self.closed:
                SubService.close(self)
                fs.base.FS.close(self)

        def __del__(self):
            self.close()

        def dispatch_paths(self, cmd_id, *paths):
            return self.dispatch(cmd_id,
                buffers=tuple(
                    (self.PathType(*path.encode()), SfBufferAttr.HipcPointer)
                    for path in paths
                )
            )

        def create_file(self, path, size=0, big=False):
            class In(LittleEndianStructure):
                _fields_ = [
                    ("option", c_uint32),
                    ("size",   c_int64),
                ]

            option = 0
            if big:
                option |= util.bit(0)

            self.dispatch(0, In(option, size),
                buffers=(
                    (self.PathType(*path.encode()), SfBufferAttr.HipcPointer),
                )
            )

        def delete_file(self, path):
            self.dispatch_paths(1, path)

        def create_dir(self, path):
            self.dispatch_paths(2, path)

        def delete_dir(self, path, recursive=True):
            if recursive:
                self.dispatch_paths(4, path)
            else:
                self.dispatch_paths(3, path)

        def rename_file(self, old, new):
            self.dispatch_paths(5, old, new)

        def rename_dir(self, old, new):
            self.dispatch_paths(6, old, new)

        def is_file(self, path):
            out = self.dispatch(7, None, c_uint32,
                buffers=(
                    (self.PathType(*path.encode()), SfBufferAttr.HipcPointer),
                )
            )

            return out["out"].value == 1

        def open_file(self, path, mode="r"):
            real_mode = 0
            for c in mode:
                if c == "r":
                    real_mode |= util.bit(0)
                elif c == "w" or c == "a":
                    real_mode |= util.bit(1, 2)

            out = self.dispatch(8, c_uint32(real_mode),
                buffers=(
                    (self.PathType(*path.encode()), SfBufferAttr.HipcPointer),
                ),
                out_num_objects=1
            )

            return self.File(mode, self, out["objects"][0])

        def open_dir(self, path, mode=None):
            if mode is None:
                mode = util.bit(0, 1)

            out = self.dispatch(9, c_uint32(mode),
                buffers=(
                    (self.PathType(*path.encode()), SfBufferAttr.HipcPointer),
                ),
                out_num_objects=1
            )

            return self.Directory(self, out["objects"][0])

        def commit(self):
            self.dispatch(10)

        def free_space(self, path="/"):
            out = self.dispatch(11, None, c_int64,
                buffers=(
                    (self.PathType(*path.encode()), SfBufferAttr.HipcPointer),
                )
            )

            return out["out"].value

        def total_space(self, path="/"):
            out = self.dispatch(12, None, c_int64,
                buffers=(
                    (self.PathType(*path.encode()), SfBufferAttr.HipcPointer),
                )
            )

            return out["out"].value

        def clean_dir(self, path):
            if self.version < (3,0,0):
                raise ValueError("Version too low")

            self.dispatch_paths(13, path)

        def get_file_timestamp(self, path):
            if self.version < (3,0,0):
                raise ValueError("Version too low")

            out = self.dispatch(14, None, self.FileTimestamp,
                buffers=(
                    (self.PathType(*path.encode()), SfBufferAttr.HipcPointer),
                )
            )

            return out["out"]

        # Essential FS methods

        def getinfo(self, path, namespaces=None):
            if path[0] != "/":
                path = "/" + path

            if namespaces is None:
                namespaces = []

            try:
                raw_info = {
                    "basic": {
                        "name":   path.split("/")[-1],
                        "is_dir": not self.is_file(path),
                    },
                }

                if len(namespaces) > 0:
                    if raw_info["basic"]["is_dir"]:
                        type = fs.enums.ResourceType.directory
                        ts = self.FileTimestamp()
                        size = 0
                    else:
                        type = fs.enums.ResourceType.file
                        ts = self.get_file_timestamp(path)

                        with self.open_file(path) as f:
                            size = f.size()

                    for n in namespaces:
                        if n == "details":
                            raw_info["details"] = {
                                "accessed":         dt.datetime.fromtimestamp(ts.accessed),
                                "created":          dt.datetime.fromtimestamp(ts.created),
                                "metadata_changed": None,
                                "modified":         dt.datetime.fromtimestamp(ts.modified),
                                "size":             size,
                                "type":             type,
                            }
                        elif n == "stat":
                            if raw_info["basic"]["is_dir"]:
                                raw_info["stat"] = {
                                    "st_mode":  stat.S_IFDIR | stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO,
                                    "st_ino":   0,
                                    "st_dev":   0,
                                    "st_nlink": 1,
                                    "st_uid":   0,
                                    "st_gid":   0,
                                    "st_size":  0,
                                    "st_atime": 0,
                                    "st_mtime": 0,
                                    "st_ctime": 0,
                                }
                            else:
                                raw_info["stat"] = {
                                    "st_mode":  stat.S_IFREG | stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH | stat.S_IWOTH,
                                    "st_ino":   0,
                                    "st_dev":   0,
                                    "st_nlink": 1,
                                    "st_uid":   0,
                                    "st_gid":   0,
                                    "st_size":  size,
                                    "st_atime": ts.accessed,
                                    "st_mtime": ts.modified,
                                    "st_ctime": ts.created,
                                }

                return fs.info.Info(raw_info)
            except ResultException as e:
                if e.result == 0x202:
                    raise fs.errors.ResourceNotFound(path)
                else:
                    raise e

        def listdir(self, path):
            if path[0] != "/":
                path = "/" + path

            try:
                if self.is_file(path):
                    raise fs.errors.DirectoryExpected(path)

                with self.open_dir(path) as d:
                    entries = d.read()

                return [x.name for x in entries]
            except ResultException as e:
                if e.result == 0x202:
                    raise fs.errors.ResourceNotFound(path)
                else:
                    raise e

        def makedir(self, path, permissions=None, recreate=False):
            if path[0] != "/":
                path = "/" + path

            try:
                self.create_dir(path)

                return fs.subfs.SubFS(self, path)
            except ResultException as e:
                if e.result == 0x202:
                    raise fs.errors.ResourceNotFound(path)
                elif e.result == 0x402:
                    if not recreate:
                        raise fs.errors.DirectoryExists(path)
                else:
                    raise e

        def openbin(self, path, mode="r", buffering=-1, **options):
            if path[0] != "/":
                path = "/" + path

            try:
                mode_tmp = ""

                for c in mode:
                    if c == "r" in mode:
                        if not self.is_file(path):
                            raise fs.errors.FileExpected(path)

                        mode_tmp += "r"
                    elif c == "w":
                        try:
                            self.delete_file(path)
                        except:
                            pass

                        self.create_file(path)
                        mode_tmp += "w"
                    elif c == "a":
                        try:
                            self.create_file(path)
                        except:
                            pass

                        mode_tmp += "a"
                    elif c == "+":
                        if "r" in mode_tmp:
                            mode_tmp += "w"
                        elif "w" in mode_tmp or "a" in mode_tmp:
                            mode_tmp += "r"

                return self.open_file(path, mode_tmp)

            except ResultException as e:
                if e.result == 0x202:
                    raise fs.errors.ResourceNotFound(path)
                else:
                    raise e

        def remove(self, path):
            if path[0] != "/":
                path = "/" + path

            try:
                if not self.is_file(path):
                    raise fs.errors.FileExpected(path)

                self.delete_file(path)
            except ResultException as e:
                if e.result == 0x202:
                    raise fs.errors.ResourceNotFound(path)
                else:
                    raise e

        def removedir(self, path):
            if path[0] != "/":
                path = "/" + path

            if path == "/":
                raise fs.errors.RemoveRootError(path)

            try:
                if self.is_file(path):
                    raise fs.errors.DirectoryExpected(path)

                with self.open_dir(path) as dir:
                    if dir.entry_count() > 0:
                        raise fs.errors.DirectoryNotEmpty(path)

                self.delete_dir(path, False)

            except ResultException as e:
                if e.result == 0x202:
                    raise fs.errors.ResourceNotFound(path)
                else:
                    raise e

        def setinfo(self, path, info):
            if path[0] != "/":
                path = "/" + path

            try:
                for n, data in info.items():
                    if n == "basic":
                        for key, value in data.items():
                            if key == "name":
                                if self.is_file(path):
                                    self.rename_file(path, value)
                                else:
                                    self.rename_dir(path, value)
                    elif n == "details":
                        for key, value in data.items():
                            if key == "size":
                                with self.open_file(path) as f:
                                    f.truncate(value)
            except ResultException as e:
                if e.result == 0x202:
                    raise fs.errors.ResourceNotFound(path)
                else:
                    raise e

        # Non-essential FS methods

        def removetree(self, path):
            if path[0] != "/":
                path = "/" + path

            if path == "/":
                raise fs.errors.RemoveRootError(path)

            try:
                if self.is_file(path):
                    raise fs.errors.DirectoryExpected(path)

                self.delete_dir(path)

            except ResultException as e:
                if e.result == 0x202:
                    raise fs.errors.ResourceNotFound(path)
                else:
                    raise e

        def move(self, src_path, dst_path, overwrite=False):
            if src_path[0] != "/":
                src_path = "/" + src_path

            if dst_path[0] != "/":
                dst_path = "/" + dst_path

            try:
                if not self.is_file(src_path):
                    raise fs.errors.FileExpected(path)

                    if self.exists(dst_path) and not overwrite:
                        raise fs.errors.DestinationExists(dst_path)

                self.rename_file(src_path, dst_path)
            except ResultException as e:
                if e.result == 0x202:
                    raise fs.errors.ResourceNotFound(src_path)
                else:
                    raise e

        def movedir(self, src_path, dst_path, create=False):
            if src_path[0] != "/":
                src_path = "/" + src_path

            if dst_path[0] != "/":
                dst_path = "/" + dst_path

            if not self.exists(src_path):
                raise fs.errors.ResourceNotFound(src_path)

            try:
                if self.is_file(src_path):
                    raise fs.errors.DirectoryExpected(src_path)

                self.rename_dir(src_path, dst_path)
            except ResultException as e:
                if e.result == 0x202:
                    raise fs.errors.ResourceNotFound(src_path)
                else:
                    raise e

    def __init__(self, h):
        super().__init__(h)

        self.dispatch(1, c_uint64(0),
            in_send_pid=True
        )

    def is_exfat_supported(self):
        if self.version < (2,0,0):
            return False

        out = self.dispatch(27, None, c_bool)

        return out["out"].value

    def open_sd_card_fs(self):
        out = self.dispatch(18,
            out_num_objects=1
        )

        return self.FileSystem(self, out["objects"][0])

    def open_bis_fs(self, partition_id, path=""):
        if not isinstance(partition_id, int):
            partition_id = partition_id.value

        out = self.dispatch(11, c_uint32(partition_id),
            buffers=(
                (self.FileSystem.PathType(*path.encode()), SfBufferAttr.HipcPointer),
            ),
            out_num_objects=1
        )

        return self.FileSystem(self, out["objects"][0])