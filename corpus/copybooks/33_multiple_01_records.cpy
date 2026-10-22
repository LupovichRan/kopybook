      * two record layouts in one copybook (select with --record)
       01  FILE-HEADER.
           05  FH-TYPE            PIC X VALUE 'H'.
           05  FH-FILE-DATE       PIC 9(8).
           05  FH-SYSTEM          PIC X(8).
           05  FILLER             PIC X(23).
       01  FILE-DETAIL.
           05  FD-TYPE            PIC X VALUE 'D'.
           05  FD-ITEM            PIC X(10).
           05  FD-QTY             PIC S9(7) COMP-3.
           05  FD-PRICE           PIC S9(7)V99 COMP-3.
           05  FD-DESC            PIC X(21).
