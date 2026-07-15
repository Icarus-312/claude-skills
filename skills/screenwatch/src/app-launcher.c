/*
 * Screenwatch TCC anchor launcher.
 *
 * macOS binds Screen Recording and Automation (Apple Events) permissions to a
 * specific executable. If launchd ran /bin/bash directly, the permission would
 * attach to bash and every script would inherit it -- and the prompts misfire.
 * So capture runs inside a tiny app bundle whose only job is to exec the real
 * shell loop; the permission attaches to THIS binary, which never changes.
 *
 * It execs $HOME/screenwatch/bin/capture-loop.sh via /bin/bash. No arguments,
 * no network, no privileged calls. install.sh compiles and ad-hoc signs this
 * into Screenwatch.app -- the repo ships source, never a prebuilt binary, so
 * you can read exactly what gets the screen-recording grant.
 */
#include <stdlib.h>
#include <unistd.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    const char *home = getenv("HOME");
    if (!home || !*home) {
        fprintf(stderr, "screenwatch: HOME is not set\n");
        return 1;
    }

    char script[4096];
    int n = snprintf(script, sizeof(script),
                     "%s/screenwatch/bin/capture-loop.sh", home);
    if (n < 0 || (size_t)n >= sizeof(script)) {
        fprintf(stderr, "screenwatch: HOME path too long\n");
        return 1;
    }

    execl("/bin/bash", "bash", script, (char *)NULL);
    perror("screenwatch: exec /bin/bash failed");
    return 1;
}
