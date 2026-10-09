/* WPE 2.54 DRM cursor workaround: sign-extend wrapped uint32_t coordinates.
 * WPE's Cursor::x/y subtract the hotspot in uint32_t, then widen to uint64_t.
 * DRM CRTC_X/Y instead require a signed coordinate extended to 64 bits.
 * Interpose only these two properties; preserve all other property values.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <xf86drmMode.h>

static pthread_once_t once = PTHREAD_ONCE_INIT;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static drmModePropertyPtr (*get_property)(int, uint32_t);
static int (*add_property)(drmModeAtomicReqPtr, uint32_t, uint32_t, uint64_t);
static uint32_t coordinate_ids[32];
static unsigned coordinate_count;
static int reported;

static void resolve(void)
{
    get_property = dlsym(RTLD_NEXT, "drmModeGetProperty");
    add_property = dlsym(RTLD_NEXT, "drmModeAtomicAddProperty");
    if (!get_property || !add_property) {
        fputs("drm-cursor-fix: unable to resolve libdrm functions\n", stderr);
        abort();
    }
}

drmModePropertyPtr drmModeGetProperty(int fd, uint32_t id)
{
    pthread_once(&once, resolve);
    drmModePropertyPtr property = get_property(fd, id);
    if (property && (!strcmp(property->name, "CRTC_X") || !strcmp(property->name, "CRTC_Y"))) {
        pthread_mutex_lock(&lock);
        unsigned i;
        for (i = 0; i < coordinate_count; ++i)
            if (coordinate_ids[i] == id) break;
        if (i == coordinate_count && coordinate_count < 32)
            coordinate_ids[coordinate_count++] = id;
        pthread_mutex_unlock(&lock);
    }
    return property;
}

int drmModeAtomicAddProperty(drmModeAtomicReqPtr request, uint32_t object,
                            uint32_t property, uint64_t value)
{
    pthread_once(&once, resolve);
    if (value > INT32_MAX && value <= UINT32_MAX) {
        pthread_mutex_lock(&lock);
        for (unsigned i = 0; i < coordinate_count; ++i) {
            if (coordinate_ids[i] == property) {
                value = (uint64_t)(int64_t)(int32_t)(uint32_t)value;
                if (!reported) {
                    fprintf(stderr, "drm-cursor-fix: corrected wrapped cursor coordinate to %lld\n", (long long)(int64_t)value);
                    reported = 1;
                }
                break;
            }
        }
        pthread_mutex_unlock(&lock);
    }
    return add_property(request, object, property, value);
}
