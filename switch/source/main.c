#include <malloc.h>
#include <string.h>

#include <switch.h>

#define NXIPC_MODULE 396

#define MAX_READ_WRITE 0xe00

//#define DEBUG

#ifdef DEBUG

#include <stdio.h>

#define PRINTF(fmt, ...) \
    printf(fmt, ##__VA_ARGS__); \
    consoleUpdate(NULL);

#else

#define PRINTF(fmt, ...)

void __appInit() {
    smInitialize();
}

void __appExit() {
    smExit();
}

#endif

typedef enum {
    CommandId_Exit                   = 0,

    CommandId_Allocate               = 1,
    CommandId_Free                   = 2,
    CommandId_Read                   = 3,
    CommandId_Write                  = 4,

    CommandId_GetService             = 5,
    CommandId_CloseService           = 6,
    CommandId_ConvertServiceToDomain = 7,

    CommandId_DispatchToService      = 8,
} CommandId;

typedef enum {
    AllocateType_Malloc   = 0,
    AllocateType_Calloc   = 1,
    AllocateType_Memalign = 2,
} AllocateType;

Result smIsServiceRegistered(SmServiceName name, bool *out) {
    return serviceDispatchInOut(smGetServiceSession(), 65100, name, *out);
}

void usb_read(void *buf, size_t size) {
    for (size_t tmp_size = 0; tmp_size < size; tmp_size += MAX_READ_WRITE) {
        size_t to_read;
        if (size - tmp_size > MAX_READ_WRITE) {
            to_read = MAX_READ_WRITE;
        } else {
            to_read = size - tmp_size;
        }

        usbCommsRead(buf + tmp_size, to_read);
    }
}

void usb_write(const void *buf, size_t size) {
    for (size_t tmp_size = 0; tmp_size < size; tmp_size += MAX_READ_WRITE) {
        size_t to_write;
        if (size - tmp_size > MAX_READ_WRITE) {
            to_write = MAX_READ_WRITE;
        } else {
            to_write = size - tmp_size;
        }

        usbCommsWrite(buf + tmp_size, to_write);
    }
}

inline void write_result(Result rc) {
    usb_write(&rc, sizeof(rc));
}

void Allocate() {
    PRINTF("Allocate\n");

    struct {
        u8 type;
        u64 size;
    } alloc;
    usb_read(&alloc, sizeof(alloc));

    void *ptr;
    switch(alloc.type) {
        case AllocateType_Malloc: {
            ptr = malloc(alloc.size);
        } break;

        case AllocateType_Calloc: {
            ptr = calloc(1, alloc.size);
        } break;

        case AllocateType_Memalign: {
            u64 align;
            usb_read(&align, sizeof(align));

            ptr = memalign(align, alloc.size);
        } break;

        default:
            write_result(MAKERESULT(NXIPC_MODULE, 3));
            
            return;
    }

    if (ptr == NULL) {
        write_result(MAKERESULT(NXIPC_MODULE, 4));

        return;
    }

    write_result(0);

    usb_write(&ptr, sizeof(ptr));
}

void Free() {
    PRINTF("Free\n");

    void *ptr;
    usb_read(&ptr, sizeof(ptr));

    free(ptr);

    write_result(0);
}

void Read() {
    PRINTF("Read\n");

    struct {
        void *ptr;
        u64 size;
    } info;
    usb_read(&info, sizeof(info));

    PRINTF("size: %#lx\n", info.size);

    write_result(0);

    usb_write(info.ptr, info.size);
}

void Write() {
    PRINTF("Write\n");

    struct {
        void *ptr;
        u64 size;
    } info;
    usb_read(&info, sizeof(info));

    usb_read(info.ptr, info.size);

    write_result(0);
}

void GetService() {
    PRINTF("GetService\n");

    SmServiceName name;
    usb_read(&name, sizeof(name));

    bool registered;
    Result rc = smIsServiceRegistered(name, &registered);
    if (R_FAILED(rc)) {
        write_result(rc);
        return;
    }

    if (!registered) {
        write_result(MAKERESULT(NXIPC_MODULE, 1));
        return; 
    }

    Service out;
    rc = smGetServiceWrapper(&out, name);
    write_result(rc);

    if (R_SUCCEEDED(rc)) {
        usb_write(&out, sizeof(out));
    }
}

void CloseService() {
    PRINTF("CloseService\n");

    Service s;
    usb_read(&s, sizeof(s));

    serviceClose(&s);

    write_result(0);
}

void ConverServiceToDomain() {
    PRINTF("ConverServiceToDomain\n");

    Service s;
    usb_read(&s, sizeof(s));

    Result rc = serviceConvertToDomain(&s);
    write_result(rc);

    if (R_SUCCEEDED(rc)) {
        usb_write(&s, sizeof(s));
    }
}

void DispatchToService() {
    PRINTF("DispatchToService\n");

    struct {
        Service s;
        u32 request_id;
        u32 in_size;
        u32 out_size;

        Handle target_session;
        u32 context;
        u8 num_buffers;
        bool in_send_pid;
        u8 in_num_objects;
        u8 in_num_handles;
        u32 out_num_objects;
        u8 out_num_handles;
    } header;
    usb_read(&header, sizeof(header));

    u8 in_data[header.in_size];
    usb_read(in_data, header.in_size);

    u8 out_data[header.out_size];

    Service out_objects[header.out_num_objects];

    SfDispatchParams params = {
        .target_session  = header.target_session,
        .context         = header.context,
        
        .in_send_pid     = header.in_send_pid,

        .in_num_objects  = header.in_num_objects,

        .out_num_objects = header.out_num_objects,
        .out_objects     = out_objects,

        .in_num_handles  = header.in_num_handles,
    };

    u32 *buffer_attrs = (u32 *) &params.buffer_attrs;
    
    bool buffer_is_pointer[header.num_buffers];
    memset(buffer_is_pointer, 0, sizeof(buffer_is_pointer));

    for (int i = 0; i < header.num_buffers; i++) {
        struct {
            u64 size;
            u32 attr;
            bool is_pointer;
        } buffer;
        usb_read(&buffer, sizeof(buffer));

        params.buffers[i].size = buffer.size;
        
        if (buffer.is_pointer) {
            usb_read(&params.buffers[i].ptr, sizeof(void *));
            buffer_is_pointer[i] = true;
        } else {
            params.buffers[i].ptr  = malloc(buffer.size);

            if (buffer.attr & SfBufferAttr_In) {
                usb_read((void *) params.buffers[i].ptr, buffer.size);
            }
        }

        buffer_attrs[i] = buffer.attr;
    }

    for (int i = 0; i < header.in_num_handles; i++) {
        usb_read(&params.in_handles[i], sizeof(Handle));
    }

    Result rc = serviceDispatchImpl(&header.s, header.request_id, in_data, header.in_size, out_data, header.out_size, params);
    write_result(rc);

    if (R_SUCCEEDED(rc)) {
        usb_write(out_data, header.out_size);

        if (header.out_num_objects > 0) {
            usb_write(out_objects, header.out_num_objects * sizeof(Service));
        }

        for (int i = 0; i < header.num_buffers; i++) {
            if (buffer_attrs[i] & SfBufferAttr_Out) {
                usb_write(params.buffers[i].ptr, params.buffers[i].size);
            }
        }
    }

    for (int i = 0; i < header.num_buffers; i++) {
        if (buffer_is_pointer[i]) {
            continue;
        }

        free((void *) params.buffers[i].ptr);
    }
}

int main(int argc, char **argv) {
    #ifdef DEBUG

    consoleInit(NULL);

    #endif

    usbCommsInitialize();

    while (appletMainLoop()) {
        PRINTF("loop\n");
        u8 cmd_id;
        usb_read(&cmd_id, sizeof(cmd_id));
        PRINTF("%d\n", cmd_id);

        bool should_break = false;

        switch(cmd_id) {
            case CommandId_Exit:
                write_result(0);

                should_break = true;

                break;

            case CommandId_Allocate:
                Allocate();
                break;

            case CommandId_Free:
                Free();
                break;

            case CommandId_Read:
                Read();
                break;

            case CommandId_Write:
                Write();
                break;

            case CommandId_GetService:
                GetService();
                break;

            case CommandId_CloseService:
                CloseService();
                break;

            case CommandId_ConvertServiceToDomain:
                ConverServiceToDomain();
                break;

            case CommandId_DispatchToService:
                DispatchToService();
                break;

            default:
                PRINTF("Invalid command\n");
                write_result(MAKERESULT(NXIPC_MODULE, 2));

                break;
        }

        if (should_break)
            break;
    }
    
    usbCommsExit();

    #ifdef DEBUG

    while (appletMainLoop()) {
        hidScanInput();
        u64 kDown = hidKeysDown(CONTROLLER_P1_AUTO);

        if (kDown & KEY_PLUS)
            break;
    }

    consoleExit(NULL);

    #endif

    return 0;
}