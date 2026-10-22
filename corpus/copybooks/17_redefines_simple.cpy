       01  REDEF-REC.
           05  RAW-KEY            PIC X(8).
           05  NUM-KEY REDEFINES RAW-KEY PIC 9(8).
           05  AMOUNT-TEXT        PIC X(4).
           05  AMOUNT-BIN REDEFINES AMOUNT-TEXT PIC S9(9) COMP.
