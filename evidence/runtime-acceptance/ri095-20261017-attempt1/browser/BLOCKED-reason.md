Browser probe BLOCKED (2026-10-17T12:46:25+08:00)
Reason: Chromium sandbox cannot start in container.
  FATAL:zygote_host_impl_linux.cc: No usable sandbox!
Host kernel: 6.8.0-147-generic
apparmor_restrict_unprivileged_userns=1
unprivileged_userns_clone=1
Per README: retain Chromium sandbox; if host seccomp/userns unsupported -> BLOCKED; do NOT use --no-sandbox.
