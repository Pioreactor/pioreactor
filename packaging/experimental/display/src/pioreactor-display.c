#include <wpe/webkit.h>
#include <glib-unix.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>

static GMainLoop *loop;
static const char *uri;
static guint retry_source;
static int result;
static gboolean smoke;

static gboolean stop(gpointer data)
{
    (void)data;
    g_main_loop_quit(loop);
    return G_SOURCE_REMOVE;
}

static gboolean retry(gpointer data)
{
    retry_source = 0;
    webkit_web_view_load_uri(WEBKIT_WEB_VIEW(data), uri);
    return G_SOURCE_REMOVE;
}

static gboolean failed(WebKitWebView *view, WebKitLoadEvent event,
                       const char *failed_uri, GError *error, gpointer data)
{
    (void)event; (void)data;
    if (g_error_matches(error, WEBKIT_NETWORK_ERROR, WEBKIT_NETWORK_ERROR_CANCELLED))
        return FALSE;
    g_warning("Load failed for %s: %s; retrying in 5 seconds", failed_uri, error->message);
    if (!retry_source)
        retry_source = g_timeout_add_seconds(5, retry, view);
    return TRUE;
}

static void terminated(WebKitWebView *view, WebKitWebProcessTerminationReason reason, gpointer data)
{
    (void)view; (void)data;
    g_warning("Web process terminated (reason %d); requesting service restart", reason);
    result = EXIT_FAILURE;
    g_main_loop_quit(loop);
}

static void inspected(GObject *object, GAsyncResult *async_result, gpointer data)
{
    (void)data;
    GError *error = NULL;
    JSCValue *value = webkit_web_view_evaluate_javascript_finish(WEBKIT_WEB_VIEW(object), async_result, &error);
    if (error) {
        g_warning("Page inspection failed: %s", error->message);
        g_error_free(error);
        return;
    }
    gchar *text = jsc_value_to_string(value);
    g_message("Page inspection: %s", text);
    if (smoke && strstr(text, "\"appRendered\":true")) {
        result = EXIT_SUCCESS;
        g_main_loop_quit(loop);
    }
    g_free(text);
    g_object_unref(value);
}

static gboolean inspect(gpointer data)
{
    webkit_web_view_evaluate_javascript(WEBKIT_WEB_VIEW(data),
        "JSON.stringify({title:document.title,url:location.href,"
        "appRendered:!!document.querySelector('#root')?.children.length,"
        "text:document.body.innerText.slice(0,300)})", -1, NULL, NULL, NULL, inspected, NULL);
    return smoke ? G_SOURCE_CONTINUE : G_SOURCE_REMOVE;
}

static void loaded(WebKitWebView *view, WebKitLoadEvent event, gpointer data)
{
    (void)data;
    if (event == WEBKIT_LOAD_FINISHED) {
        g_message("Page loaded: %s", webkit_web_view_get_uri(view));
        g_timeout_add_seconds(5, inspect, view);
    }
}

int main(int argc, char **argv)
{
    if (argc > 1 && !strcmp(argv[1], "--version")) {
        g_print("pioreactor-display (WPE %u.%u.%u)\n", webkit_get_major_version(),
                webkit_get_minor_version(), webkit_get_micro_version());
        return EXIT_SUCCESS;
    }
    smoke = argc > 1 && !strcmp(argv[1], "--smoke-test");
    uri = argc > (smoke ? 2 : 1) ? argv[smoke ? 2 : 1] : "http://localhost/";
    if (!g_str_has_prefix(uri, "http://") && !g_str_has_prefix(uri, "https://")) {
        g_printerr("Usage: pioreactor-display [--smoke-test] [http(s)://URL]\n");
        return EXIT_FAILURE;
    }
    if (!g_getenv("WPE_PLATFORM"))
        g_setenv("WPE_PLATFORM", "drm", TRUE);
    g_message("Starting WPE %u.%u.%u; platform=%s; URL=%s",
              webkit_get_major_version(), webkit_get_minor_version(), webkit_get_micro_version(),
              g_getenv("WPE_PLATFORM"), uri);
    loop = g_main_loop_new(NULL, FALSE);
    WebKitWebView *view = WEBKIT_WEB_VIEW(g_object_new(WEBKIT_TYPE_WEB_VIEW, NULL));
    g_signal_connect(view, "load-failed", G_CALLBACK(failed), NULL);
    g_signal_connect(view, "load-changed", G_CALLBACK(loaded), NULL);
    g_signal_connect(view, "web-process-terminated", G_CALLBACK(terminated), NULL);
    g_unix_signal_add(SIGTERM, stop, NULL);
    g_unix_signal_add(SIGINT, stop, NULL);
    if (smoke) {
        result = EXIT_FAILURE;
        g_timeout_add_seconds(60, stop, NULL);
    }
    webkit_web_view_load_uri(view, uri);
    g_main_loop_run(loop);
    if (retry_source)
        g_source_remove(retry_source);
    g_object_unref(view);
    g_main_loop_unref(loop);
    return result;
}
