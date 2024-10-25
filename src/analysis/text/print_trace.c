#include <assert.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>

#include <glib.h>

#include "file/file.h"
#include "io/io.h"
#include "logger/logger.h"
#include "trace/reader.h"
#include "trace/trace.h"

struct CommandLineArguments {
    char *executable;
    gchar *input_path;
    enum TraceFormat trace_format;
    gint64 start;
    gint64 length;
};

/// @note   Copired from '//src/run/generate_mrc.c'. Adapted for this use case.
static struct CommandLineArguments
parse_command_line_arguments(int argc, char *argv[])
{
    gchar *help_msg = NULL;

    // Set defaults.
    struct CommandLineArguments args = {.executable = argv[0],
                                        .input_path = NULL,
                                        .trace_format = TRACE_FORMAT_KIA,
                                        .start = 0,
                                        .length = 10};
    gchar *trace_format = NULL;

    // Command line options.
    GOptionEntry entries[] = {
        // Arguments related to the input generation
        {"input",
         'i',
         0,
         G_OPTION_ARG_FILENAME,
         &args.input_path,
         "path to the input trace",
         NULL},
        {"format",
         'f',
         0,
         G_OPTION_ARG_STRING,
         &trace_format,
         "format of the input trace. Options: {Kia,Sari}. Default: Kia.",
         NULL},
        {"start",
         's',
         0,
         G_OPTION_ARG_INT64,
         &args.start,
         "index to begin. Default 0.",
         NULL},
        {"length",
         'l',
         0,
         G_OPTION_ARG_INT64,
         &args.length,
         "length to print. Default 10.",
         NULL},
        G_OPTION_ENTRY_NULL,
    };

    GError *error = NULL;
    GOptionContext *context;
    context = g_option_context_new("- print rows of a trace");
    g_option_context_add_main_entries(context, entries, NULL);
    if (!g_option_context_parse(context, &argc, &argv, &error)) {
        g_print("option parsing failed: %s\n", error->message);
        goto cleanup;
    }
    // Come on, GLib! The 'g_option_context_parse' changes the errno to
    // 2 and leaves it for me to clean up. Or maybe I'm using it wrong.
    errno = 0;

    // Check the arguments for correctness.
    if (args.input_path == NULL || !file_exists(args.input_path)) {
        LOGGER_ERROR("input trace path '%s' DNE",
                     args.input_path == NULL ? "(null)" : args.input_path);
        goto cleanup;
    }
    if (trace_format != NULL) {
        args.trace_format = parse_trace_format_string(trace_format);
        if (args.trace_format == TRACE_FORMAT_INVALID) {
            LOGGER_ERROR("invalid trace format '%s'", trace_format);
            goto cleanup;
        }
    } else {
        // NOTE If 'trace_format' is NULL, the we remain with the default.
        LOGGER_TRACE("using default trace format");
    }
    if (args.start < 0) {
        // TODO(dchu):  We can support wraparound, similarly to Python's
        //              indexing.
        LOGGER_ERROR("cannot start at a negative index!");
        goto cleanup;
    }
    if (args.length <= 0) {
        // TODO(dchu):  Check that this doesn't exceed the bounds of the
        //              array.
        LOGGER_ERROR("must have positive length!");
        goto cleanup;
    }

    g_option_context_free(context);
    return args;
cleanup:
    help_msg = g_option_context_get_help(context, FALSE, NULL);
    g_print("%s", help_msg);
    free(help_msg);
    g_option_context_free(context);
    exit(-1);
}

static void
print_trace_entry(struct FullTraceItem const item)
{
    fprintf(stdout,
            "%" PRIu64 " %" PRIu8 " %" PRIu64 " %" PRIu32 " %" PRIu32 "\n",
            item.timestamp,
            item.command,
            item.key,
            item.size,
            item.time_to_live);
}

static bool
run(struct CommandLineArguments const *const args)
{
    struct MemoryMap mm = {0};
    size_t bytes_per_trace_item = 0;
    size_t num_entries = 0;
    size_t start = 0, length = 0, end = 0;

    if (args == NULL) {
        LOGGER_ERROR("args is NULL");
        goto cleanup_error;
    }

    LOGGER_INFO("CommandLineArguments(executable='%s', input='%s', "
                "trace_format='%s', start=%" PRId64 ", length=%" PRId64 ")",
                args->executable,
                args->input_path,
                TRACE_FORMAT_STRINGS[args->trace_format],
                args->start,
                args->length);
    bytes_per_trace_item = get_bytes_per_trace_item(args->trace_format);
    if (bytes_per_trace_item == 0) {
        LOGGER_ERROR("invalid input", args->trace_format);
        goto cleanup_error;
    }

    // Memory map the input trace file
    if (!MemoryMap__init(&mm, args->input_path, "rb")) {
        LOGGER_ERROR("failed to mmap '%s'", args->input_path);
        goto cleanup_error;
    }
    num_entries = mm.num_bytes / bytes_per_trace_item;

    start = args->start;
    length = args->length;
    end = args->start + args->length;
    if (start >= num_entries || start + length > num_entries) {
        LOGGER_ERROR(
            "invalid start (%zu) or length (%zu) for number of entries (%zu)",
            start,
            length,
            num_entries);
    }
    fprintf(stdout, "Timestamp Command Key Size TTL\n");
    for (size_t i = start; i < end; ++i) {
        struct FullTraceItem item = construct_full_trace_item(
            &((uint8_t *)mm.buffer)[i * bytes_per_trace_item],
            args->trace_format);
        print_trace_entry(item);
    }

    MemoryMap__destroy(&mm);
    return true;
cleanup_error:
    MemoryMap__destroy(&mm);
    return false;
}

int
main(int argc, char **argv)
{
    struct CommandLineArguments args = parse_command_line_arguments(argc, argv);
    if (!run(&args)) {
        LOGGER_ERROR("runner failed");
        return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
}
