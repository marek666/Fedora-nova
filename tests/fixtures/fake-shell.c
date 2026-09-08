#include <gio/gio.h>
#include <glib-unix.h>
#include <signal.h>
#include <sys/wait.h>
#include <unistd.h>

static GMainLoop *loop;
static char *close_path;
static gboolean quit(gpointer unused) { (void) unused; g_main_loop_quit(loop); return G_SOURCE_REMOVE; }
static gboolean check_close(gpointer unused) {
    (void) unused;
    if (g_file_test(close_path, G_FILE_TEST_EXISTS)) return quit(NULL);
    return G_SOURCE_CONTINUE;
}
int main(int argc, char **argv) {
    if (argc == 2 && !g_strcmp0(argv[1], "--version")) { g_print("GNOME Shell 50.0\n"); return 0; }
    if (argc != 3 || g_strcmp0(argv[1], "--devkit") || g_strcmp0(argv[2], "--wayland")) return 2;
    const char *root = g_getenv("NOVA_TEST_DIR");
    if (!root) return 2;
    GError *error = NULL;
    GDBusConnection *bus = g_bus_get_sync(G_BUS_TYPE_SESSION, NULL, &error);
    if (!bus) { g_printerr("%s\n", error->message); return 2; }
    GVariant *result = g_dbus_connection_call_sync(bus, "org.freedesktop.DBus", "/org/freedesktop/DBus",
        "org.freedesktop.DBus", "RequestName", g_variant_new("(su)", "org.gnome.Shell", 4u),
        G_VARIANT_TYPE("(u)"), G_DBUS_CALL_FLAGS_NONE, 1000, NULL, &error);
    if (!result) return 2;
    guint status;
    g_variant_get(result, "(u)", &status);
    g_variant_unref(result);
    if (status != 1) return 2;
    pid_t child = fork();
    if (child == 0) { execl("/usr/bin/sleep", "dconf-service", "600", NULL); _exit(2); }
    char *record = g_strdup_printf("%d %d\n", getpid(), child);
    char *path = g_strdup_printf("%s/ready", root);
    g_file_set_contents(path, record, -1, &error);
    g_free(path); g_free(record);
    close_path = g_strdup_printf("%s/close", root);
    loop = g_main_loop_new(NULL, FALSE);
    g_unix_signal_add(SIGTERM, quit, NULL);
    g_unix_signal_add(SIGINT, quit, NULL);
    g_timeout_add(20, check_close, NULL);
    g_main_loop_run(loop);
    kill(child, SIGTERM); waitpid(child, NULL, 0);
    g_dbus_connection_close_sync(bus, NULL, NULL);
    g_object_unref(bus); g_main_loop_unref(loop); g_free(close_path);
    return 0;
}
