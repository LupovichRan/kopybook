      * COMP = binary, value limited to PIC digits (TRUNC(STD))
       01  COMP-REC.
           05  HALF-S             PIC S9(4)    COMP.
           05  HALF-U             PIC 9(4)     COMP.
           05  FULL-S             PIC S9(9)    COMP.
           05  FULL-U             PIC 9(9)     COMP.
           05  DBL-S              PIC S9(18)   COMP.
           05  DBL-U              PIC 9(18)    COMP.
           05  SMALL              PIC S9(2)    COMP.
           05  PRICE              PIC S9(7)V99 COMP.
