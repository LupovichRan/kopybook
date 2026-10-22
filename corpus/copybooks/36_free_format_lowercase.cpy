*> free-format source, lower case, floating comments
01 free-rec.
   05 rec-id pic x(6).   *> identifier
   05 amount pic s9(5)v99 comp-3.
   05 items occurs 2 times.
      10 item-code pic xx.
      10 item-qty  pic 9(3).
