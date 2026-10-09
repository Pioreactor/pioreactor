PKGS = wpe-webkit-2.0 wpe-platform-2.0
CFLAGS += -O2 -Wall -Wextra -Werror

all: pioreactor-display libpioreactor-drm-cursor-fix.so

pioreactor-display: src/pioreactor-display.c
	$(CC) $(CFLAGS) $< -o $@ $(shell pkg-config --cflags --libs $(PKGS))

libpioreactor-drm-cursor-fix.so: src/drm-cursor-fix.c
	$(CC) $(CFLAGS) -shared -fPIC $(shell pkg-config --cflags libdrm) $< -o $@ -ldl -pthread

install: all libpioreactor-drm-cursor-fix.so
	install -Dm755 pioreactor-display $(DESTDIR)/usr/local/bin/pioreactor-display

	install -Dm755 libpioreactor-drm-cursor-fix.so $(DESTDIR)/usr/local/lib/libpioreactor-drm-cursor-fix.so

clean:
	rm -f pioreactor-display libpioreactor-drm-cursor-fix.so

.PHONY: all install clean
