       01  ODO-REC.
           05  ACCT               PIC 9(8).
           05  TXN-COUNT          PIC S9(4) COMP.
           05  TXN-AMOUNT         PIC S9(7)V99 COMP-3
                                  OCCURS 0 TO 20 TIMES
                                  DEPENDING ON TXN-COUNT.
