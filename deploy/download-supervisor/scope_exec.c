/*
 * Start one command atomically inside an existing cgroup v2 scope.
 * Build and install as a root-owned, non-writable supervisor helper. This
 * binary grants no capabilities and accepts no shell command string.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/sched.h>
#include <limits.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define DOWNLOAD_UID 10001
#define DOWNLOAD_GID 10001

static void child_error(const char *message) {
    ssize_t ignored = write(STDERR_FILENO, message, strlen(message));
    (void)ignored;
    _exit(127);
}

static void close_child_fds(void) {
#ifdef SYS_close_range
    if (syscall(SYS_close_range, 3U, UINT_MAX, 0U) == 0) {
        return;
    }
#endif
    struct rlimit limit;
    if (getrlimit(RLIMIT_NOFILE, &limit) != 0) {
        child_error("scope-exec: getrlimit failed\n");
    }
    rlim_t end = limit.rlim_cur;
    if (end > 1048576U) {
        end = 1048576U;
    }
    for (int fd = 3; (rlim_t)fd < end; ++fd) {
        (void)close(fd);
    }
}

int main(int argc, char **argv) {
    if (argc < 5 || strcmp(argv[1], "--cgroup") != 0 || strcmp(argv[3], "--") != 0) {
        (void)fprintf(stderr, "usage: scope-exec --cgroup PATH -- PROGRAM [ARG ...]\n");
        return 64;
    }

    int cgroup_fd = open(argv[2], O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (cgroup_fd < 0) {
        (void)fprintf(stderr, "scope-exec: cannot open cgroup: %s\n", strerror(errno));
        return 73;
    }

    if (prctl(PR_SET_PDEATHSIG, SIGKILL) != 0 || getppid() == 1) {
        (void)close(cgroup_fd);
        return 70;
    }

    int pidfd = -1;
    struct clone_args args;
    memset(&args, 0, sizeof(args));
    args.flags = CLONE_INTO_CGROUP | CLONE_PIDFD;
    args.pidfd = (uintptr_t)&pidfd;
    args.exit_signal = SIGCHLD;
    args.cgroup = (uint64_t)cgroup_fd;

    pid_t child = (pid_t)syscall(SYS_clone3, &args, sizeof(args));
    if (child == 0) {
        if (prctl(PR_SET_PDEATHSIG, SIGKILL) != 0 || getppid() == 1) {
            child_error("scope-exec: parent disappeared\n");
        }
        close_child_fds();
        if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0 ||
            setgroups(0, NULL) != 0 || setresgid(DOWNLOAD_GID, DOWNLOAD_GID, DOWNLOAD_GID) != 0 ||
            setresuid(DOWNLOAD_UID, DOWNLOAD_UID, DOWNLOAD_UID) != 0) {
            child_error("scope-exec: privilege drop failed\n");
        }
        int null_fd = open("/dev/null", O_RDWR);
        if (null_fd < 0 || dup2(null_fd, STDIN_FILENO) < 0 ||
            dup2(null_fd, STDOUT_FILENO) < 0 ||
            dup2(null_fd, STDERR_FILENO) < 0) {
            child_error("scope-exec: stdio isolation failed\n");
        }
        if (null_fd > STDERR_FILENO) {
            (void)close(null_fd);
        }
        char *const empty_environment[] = {NULL};
        execve(argv[4], &argv[4], empty_environment);
        child_error("scope-exec: execve failed\n");
    }
    (void)close(cgroup_fd);
    if (child < 0) {
        (void)fprintf(stderr, "scope-exec: clone3 failed: %s\n", strerror(errno));
        return errno == ENOSYS ? 78 : 73;
    }
    if (pidfd < 0) {
        (void)kill(child, SIGKILL);
        (void)waitpid(child, NULL, 0);
        return 70;
    }
    (void)close(pidfd);

    if (dprintf(STDOUT_FILENO, "%ld\n", (long)child) < 0) {
        (void)kill(child, SIGKILL);
        (void)waitpid(child, NULL, 0);
        return 74;
    }

    int status = 0;
    while (waitpid(child, &status, 0) < 0) {
        if (errno != EINTR) {
            return 70;
        }
    }
    if (WIFEXITED(status)) {
        return WEXITSTATUS(status);
    }
    if (WIFSIGNALED(status)) {
        return 128 + WTERMSIG(status);
    }
    return 70;
}
