       01  ORDER-REC.
           05  ORDER-ID           PIC X(10).
           05  LINE-ITEM OCCURS 4 TIMES.
               10  SKU            PIC X(8).
               10  QTY            PIC S9(4) COMP.
               10  UNIT-PRICE     PIC S9(5)V99 COMP-3.
           05  ORDER-TOTAL        PIC S9(9)V99 COMP-3.
