       01  OCCURS-REC.
           05  CUST-ID            PIC 9(6).
           05  MONTHLY-TOTAL      PIC S9(7)V99 COMP-3 OCCURS 12 TIMES.
           05  FLAGS              PIC X OCCURS 8.
           05  SCORES             PIC 9(3) OCCURS 5 TIMES
                                  INDEXED BY SC-IDX.
