# Master Makefile v koreni projektu

all:
	$(MAKE) -C sw all

hw:
	$(MAKE) -C sw hw

sw:
	$(MAKE) -C sw software.hex

clean:
	$(MAKE) -C sw clean

.PHONY: all hw sw clean
