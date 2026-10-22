      * record-type discriminator with three layouts in one area
       01  MULTI-REC.
           05  REC-TYPE           PIC X.
               88  IS-PAYMENT     VALUE 'P'.
               88  IS-REFUND      VALUE 'R'.
               88  IS-NOTE        VALUE 'N'.
           05  PAYMENT-DATA.
               10  PAY-AMOUNT     PIC S9(9)V99 COMP-3.
               10  PAY-METHOD     PIC XX.
               10  PAY-REF        PIC X(10).
           05  REFUND-DATA REDEFINES PAYMENT-DATA.
               10  REF-AMOUNT     PIC S9(9)V99 COMP-3.
               10  REF-REASON     PIC 9(3).
           05  NOTE-DATA REDEFINES PAYMENT-DATA.
               10  NOTE-TEXT      PIC X(18).
           05  SEQ-NO             PIC 9(6).
