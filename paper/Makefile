# Makefile for IEEE-format reproduction paper
# Targets: all (PDF), clean, view

MAIN = main
TEX  = $(MAIN).tex
BIB  = refs.bib

.PHONY: all clean view

all: $(MAIN).pdf

$(MAIN).pdf: $(TEX) $(BIB) $(wildcard figures/*.png)
	pdflatex $(MAIN)
	bibtex $(MAIN)
	pdflatex $(MAIN)
	pdflatex $(MAIN)

view: $(MAIN).pdf
	@if command -v xdg-open >/dev/null; then xdg-open $(MAIN).pdf & \
	elif command -v open >/dev/null; then open $(MAIN).pdf; \
	else start $(MAIN).pdf; fi

clean:
	rm -f $(MAIN).aux $(MAIN).bbl $(MAIN).blg $(MAIN).log \
	      $(MAIN).out $(MAIN).toc $(MAIN).synctex.gz $(MAIN).pdf
