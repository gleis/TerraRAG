#include <errno.h>
#include <stdio.h>

/* Exercise the rejected charset boundary fixed by CVE-2026-18374 and a
 * legitimate conversion through the same libc entry point. */
int main(void) {
    const char *invalid[] = {"r,ccs=", "r,ccs= ", "r,ccs=\t", "r,ccs=//"};
    for (unsigned repeat = 0; repeat < 1000; ++repeat) {
        for (unsigned i = 0; i < sizeof invalid / sizeof invalid[0]; ++i) {
            errno = 0;
            FILE *file = fopen("/dev/null", invalid[i]);
            if (file != NULL || errno != EINVAL) {
                fprintf(stderr, "Invalid charset was not rejected with EINVAL\n");
                if (file != NULL) fclose(file);
                return 1;
            }
        }
    }
    FILE *file = fopen("/dev/null", "r,ccs=UTF-8");
    if (file == NULL) return 2;
    fclose(file);
    puts("libc invalid-charset guard and valid UTF-8 conversion passed");
    return 0;
}
