       01  CLAIM-REC.
           05  CLAIM-ID           PIC X(12).
           05  LINE-COUNT         PIC 99.
           05  CLAIM-LINE OCCURS 1 TO 15 TIMES DEPENDING ON LINE-COUNT.
               10  PROC-CODE      PIC X(5).
               10  BILLED         PIC S9(7)V99 COMP-3.
               10  PAID           PIC S9(7)V99 COMP-3.
               10  DENIED-FLAG    PIC X.
                   88  DENIED     VALUE 'Y'.
