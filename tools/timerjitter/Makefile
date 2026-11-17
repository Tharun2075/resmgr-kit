# Build with the QNX SDP environment sourced: make
CC = qcc -Vgcc_ntox86_64
CFLAGS = -Wall -O2

timerjitter: timerjitter.c
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -f timerjitter
