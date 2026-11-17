/*
 * timerjitter - measure the period of a pulse timer on a QNX target.
 *
 * Uses the same timer pattern as the code resmgr-kit generates for a spec
 * with a timer: timer_create(CLOCK_MONOTONIC) with a SIGEV_PULSE event on a
 * private channel. Each pulse is stamped with clock_gettime(CLOCK_MONOTONIC)
 * and the time between pulses is printed, one period in nanoseconds per line.
 *
 * usage: timerjitter [count] [period_us]   (defaults: 2000 periods, 10000 us)
 */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/neutrino.h>
#include <sys/siginfo.h>

#define TICK_CODE (_PULSE_CODE_MINAVAIL + 1)

static uint64_t now_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000u + (uint64_t)ts.tv_nsec;
}

int main(int argc, char **argv)
{
    long count = argc > 1 ? strtol(argv[1], NULL, 10) : 2000;
    long period_us = argc > 2 ? strtol(argv[2], NULL, 10) : 10000;
    if (count < 1 || period_us < 1) {
        fprintf(stderr, "usage: %s [count] [period_us]\n", argv[0]);
        return 2;
    }

    int chid = ChannelCreate(_NTO_CHF_PRIVATE);
    int coid = ConnectAttach(0, 0, chid, _NTO_SIDE_CHANNEL, 0);
    if (chid == -1 || coid == -1) {
        fprintf(stderr, "channel: %s\n", strerror(errno));
        return 1;
    }

    struct sigevent ev;
    SIGEV_PULSE_INIT(&ev, coid, SIGEV_PULSE_PRIO_INHERIT, TICK_CODE, 0);
    timer_t timer;
    if (timer_create(CLOCK_MONOTONIC, &ev, &timer) == -1) {
        fprintf(stderr, "timer_create: %s\n", strerror(errno));
        return 1;
    }
    struct itimerspec its = {
        .it_value = {period_us / 1000000, (period_us % 1000000) * 1000},
        .it_interval = {period_us / 1000000, (period_us % 1000000) * 1000},
    };
    if (timer_settime(timer, 0, &its, NULL) == -1) {
        fprintf(stderr, "timer_settime: %s\n", strerror(errno));
        return 1;
    }

    uint64_t *stamp = malloc((size_t)(count + 1) * sizeof *stamp);
    if (!stamp)
        return 1;
    struct _pulse pulse;
    for (long i = 0; i <= count; i++) {
        if (MsgReceivePulse(chid, &pulse, sizeof pulse, NULL) == -1) {
            fprintf(stderr, "MsgReceivePulse: %s\n", strerror(errno));
            return 1;
        }
        stamp[i] = now_ns();
    }
    timer_delete(timer);

    /* Print after the loop so printing does not disturb the measurement. */
    for (long i = 1; i <= count; i++)
        printf("%llu\n", (unsigned long long)(stamp[i] - stamp[i - 1]));
    free(stamp);
    return 0;
}
